/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import 'dotenv/config';
import * as fs from 'node:fs';
import * as path from 'node:path';

import type { DataSourceUpdateParams, DataSourceCreateParams } from 'codemie-sdk';
import { SkillVisibility } from 'codemie-sdk';
import * as yaml from 'yaml';

import type { AppConfig } from './appConfig';
import { logApiErrorDetails } from './lib/apiErrorLogger';
import {
  createAssistantAndGetId,
  assertAssistantValidationSucceeded,
  shouldRecoverAssistantCreateError,
} from './lib/assistantHelpers';
import { calculateChecksum, calculateAssistantConfigChecksum } from './lib/checksumUtils';
import { CleanupManager } from './lib/cleanupManager';
import { createClient } from './lib/clientFactory';
import {
  calculateCompanionFilesChecksum,
  calculateDatasourceConfigChecksum,
  calculateSkillConfigChecksum,
  calculateWorkflowConfigChecksum,
} from './lib/codemieConfigChecksums';
import { CodemieConfigLoader } from './lib/codemieConfigLoader';
import { datasourceResourceToCreateParams, assistantResourceToCreateParams } from './lib/converters';
import { TIMEOUTS_MS } from './lib/constants';
import { logger } from './lib/logger';
import {
  findAssistantByName,
  findDatasourceByName,
  findSkillByName,
  findWorkflowByName,
  SkillNameIndex,
} from './lib/paginationUtils';
import {
  checkAssistantExists,
  checkDatasourceExists,
  checkSkillExists,
  checkWorkflowExists,
} from './lib/resourceExistenceChecker';
import { resolveSkillIds } from './lib/resourceResolver';
import type { CompanionFile } from './lib/skillCompanionFiles';
import { hasCompanionFileLayout, collectCompanionFiles, stateHasCompanionFiles } from './lib/skillCompanionFiles';
import {
  collectAssistantIdsForDetach,
  expandAssistantsWithDependencies,
  filterAssistantsReferencingSkillGroup,
  selectSkillGroupForReplacement,
} from './lib/skillReplacement';
import { StateManager } from './lib/stateManager';
import { withTimeout } from './lib/timeoutUtils';
import { validateSkillDescriptions } from './lib/validationUtils';
import type { WorkflowYaml, ImportedResource, AssistantResource, SkillState } from './types/codemieConfig';

interface DeploymentStats {
  created: number;
  updated: number;
  unchanged: number;
  failed: number;
}

/**
 * Sort assistants by dependencies (topological sort)
 * Assistants with sub_assistants will be deployed after their dependencies
 */
export function sortAssistantsByDependencies(assistants: AssistantResource[]): AssistantResource[] {
  const sorted: AssistantResource[] = [];
  const visited = new Set<string>();
  const visiting = new Set<string>();

  const assistantMap = new Map<string, AssistantResource>();
  for (const assistant of assistants) {
    assistantMap.set(assistant.name, assistant);
  }

  function visit(name: string): void {
    if (visited.has(name)) {
      return;
    }

    if (visiting.has(name)) {
      throw new Error(`Circular dependency detected for assistant: ${name}`);
    }

    visiting.add(name);

    const assistant = assistantMap.get(name);
    if (assistant && assistant.sub_assistants) {
      for (const subName of assistant.sub_assistants) {
        if (!assistantMap.has(subName)) {
          throw new Error(
            `Sub-assistant "${subName}" referenced by "${name}" not found in config. ` +
              `Ensure all sub-assistants are defined in resources.assistants.`
          );
        }
        visit(subName);
      }
    }

    visiting.delete(name);
    visited.add(name);

    if (assistant) {
      sorted.push(assistant);
    }
  }

  for (const assistant of assistants) {
    visit(assistant.name);
  }

  return sorted;
}

/**
 * Sync skills attached to an assistant: attach new ones, detach removed ones.
 * Compares desired skill IDs against what's currently attached on the platform.
 */
async function syncAssistantSkills(
  client: Awaited<ReturnType<typeof createClient>>,
  assistantId: string,
  desiredSkillIds: string[]
): Promise<void> {
  let currentSkills: Array<{ id: string }> = [];
  try {
    currentSkills = await client.skills.getAssistantSkills(assistantId);
  } catch (fetchError) {
    logger.warn(`  ⚠️  Could not fetch current skills for assistant ${assistantId}, treating as empty`);
    logger.debug(`     ${fetchError instanceof Error ? fetchError.message : String(fetchError)}`);
  }

  const currentIds = new Set(currentSkills.map((s) => s.id));
  const desiredIds = new Set(desiredSkillIds);

  const toAttach = desiredSkillIds.filter((id) => !currentIds.has(id));
  const toDetach = currentSkills.filter((s) => !desiredIds.has(s.id)).map((s) => s.id);

  if (toAttach.length === 0 && toDetach.length === 0) {
    return;
  }

  if (toAttach.length > 0) {
    logger.info(`  Attaching ${toAttach.length} skill(s)...`);
    for (const skillId of toAttach) {
      try {
        await client.skills.attachToAssistant(assistantId, skillId);
        logger.info(`    ✓ Attached skill ${skillId}`);
      } catch (attachError) {
        const msg = attachError instanceof Error ? attachError.message : String(attachError);
        if (msg.includes('already attached') || msg.includes('already exists')) {
          logger.info(`    ✓ Skill ${skillId} already attached`);
        } else {
          throw attachError;
        }
      }
    }
  }

  if (toDetach.length > 0) {
    logger.info(`  Detaching ${toDetach.length} skill(s)...`);
    for (const skillId of toDetach) {
      try {
        await client.skills.detachFromAssistant(assistantId, skillId);
        logger.info(`    ✓ Detached skill ${skillId}`);
      } catch (detachError) {
        const msg = detachError instanceof Error ? detachError.message : String(detachError);
        if (msg.includes('not found') || msg.includes('not attached')) {
          logger.info(`    ✓ Skill ${skillId} already detached`);
        } else {
          throw detachError;
        }
      }
    }
  }
}

/**
 * Deploy all assistants from configuration
 * Extracted from main() for better maintainability
 */
// eslint-disable-next-line max-lines-per-function
export async function deployAssistants(
  config: ReturnType<CodemieConfigLoader['loadConfig']>,
  client: Awaited<ReturnType<typeof createClient>>,
  loader: CodemieConfigLoader,
  stateManager: StateManager
): Promise<DeploymentStats> {
  const stats: DeploymentStats = { created: 0, updated: 0, unchanged: 0, failed: 0 };

  if (!config.resources.assistants) {
    return stats;
  }

  logger.info('🤖 Processing assistants...\n');

  // Sort assistants by dependencies to ensure sub_assistants are deployed first
  const sortedAssistants = sortAssistantsByDependencies(config.resources.assistants);
  logger.info(`   Sorted ${sortedAssistants.length} assistant(s) by dependencies\n`);

  for (const assistant of sortedAssistants) {
    try {
      logger.info(`Processing: ${assistant.name}`);

      const promptContent = loader.loadPrompt(assistant.prompt);

      let buildConfig = null;
      if (assistant.config) {
        buildConfig = loader.loadAssistantConfig(assistant.config);
      }

      const configChecksum = calculateAssistantConfigChecksum(assistant, buildConfig);

      let resolvedAssistantIds = assistant.assistant_ids || [];

      if (assistant.sub_assistants && assistant.sub_assistants.length > 0) {
        logger.info(`  Resolving ${assistant.sub_assistants.length} sub-assistant name(s)...`);
        const resolvedIds: string[] = [];
        for (const name of assistant.sub_assistants) {
          const subAssistantState = stateManager.getAssistantState(name);
          if (!subAssistantState) {
            throw new Error(`Sub-assistant "${name}" not found in state. Ensure the assistant is deployed first.`);
          }
          resolvedIds.push(subAssistantState.id);
          logger.info(`    ✓ Resolved "${name}" → ${subAssistantState.id}`);
        }
        resolvedAssistantIds = resolvedIds;
      }

      let resolvedContext = assistant.context || [];
      if (assistant.datasource_names && assistant.datasource_names.length > 0) {
        logger.info(`  Resolving ${assistant.datasource_names.length} datasource name(s)...`);
        const datasourceContextEntries: Array<{ context_type: 'code' | 'knowledge_base'; name: string }> = [];

        // Get all datasources from config (resources + imported)
        const datasourcesInConfig = config.resources.datasources || [];
        const importedDatasources = config.imported?.datasources || [];
        const allDatasources = [...datasourcesInConfig, ...importedDatasources];

        for (const dsName of assistant.datasource_names) {
          const datasource = allDatasources.find((ds) => ds.name === dsName);
          if (!datasource) {
            throw new Error(`Datasource with name "${dsName}" not found in config (resources or imported)`);
          }

          const contextType = datasource.type === 'code' ? 'code' : 'knowledge_base';
          datasourceContextEntries.push({
            context_type: contextType,
            name: datasource.name,
          });
          logger.info(`    ✓ Resolved "${dsName}" → ${datasource.name} (${contextType})`);
        }

        resolvedContext = [...resolvedContext, ...datasourceContextEntries];
      }

      let resolvedSkillIds: string[] = [];
      if (assistant.skills && assistant.skills.length > 0) {
        logger.info(`  Resolving ${assistant.skills.length} skill name(s)...`);
        resolvedSkillIds = resolveSkillIds(assistant.skills, stateManager, config);
      }

      const assistantWithResolved = {
        ...assistant,
        assistant_ids: resolvedAssistantIds,
        context: resolvedContext,
      };
      const apiParams = assistantResourceToCreateParams(assistantWithResolved, config.project.name, promptContent);

      const existingState = stateManager.getAssistantState(assistant.name);
      let deployedAssistantId: string | null = null;

      if (existingState) {
        // Use shared logic for existence check (same as preview.ts)
        const existsOnPlatform = await checkAssistantExists(client, assistant.name, stateManager);

        if (existsOnPlatform) {
          const hasChanged =
            existingState.promptChecksum !== calculateChecksum(promptContent) ||
            existingState.configChecksum !== configChecksum;

          if (hasChanged) {
            logger.info(`  Updating assistant (ID: ${existingState.id})...`);

            if (process.env.DEBUG_API) {
              logger.debug('\n=== DEBUG: Update API Params ===');
              logger.debug(JSON.stringify(apiParams, null, 2));
              logger.debug('================================\n');
            }

            const updateResponse = await client.assistants.update(existingState.id, apiParams);
            assertAssistantValidationSucceeded(updateResponse, 'update', assistant.name);
            logger.info(`✓ Updated assistant: ${assistant.name} (${existingState.id})`);

            stateManager.updateAssistantState(assistant.name, existingState.id, promptContent, assistant, buildConfig);
            deployedAssistantId = existingState.id;

            stats.updated++;
          } else {
            logger.info(`  ✓ No changes detected (ID: ${existingState.id})`);
            deployedAssistantId = existingState.id;
            stats.unchanged++;
          }
        } else {
          logger.info(`  ⚠️  Assistant ID from state not found on platform, will create new`);
          logger.info(`  Creating new assistant...`);

          if (process.env.DEBUG_API) {
            logger.debug('\n=== DEBUG: API Params ===');
            logger.debug(JSON.stringify(apiParams, null, 2));
            logger.debug('=========================\n');
          }

          let assistantId: string;
          try {
            assistantId = await createAssistantAndGetId(client, apiParams, assistant.slug);
            logger.info(`✓ Created assistant: ${assistant.name} (${assistantId})`);
            stats.created++;
          } catch (createError) {
            if (!shouldRecoverAssistantCreateError(createError)) {
              throw createError;
            }
            logger.warn(`  ⚠️  Assistant create failed. Checking if it already exists on platform...`);

            let existingId: string | null = null;

            if (assistant.slug) {
              try {
                const existingBySlug = await client.assistants.getBySlug(assistant.slug);
                existingId = existingBySlug?.id || null;
              } catch {
                // Fall back to name lookup below
              }
            }

            if (!existingId) {
              existingId = await findAssistantByName(client, assistant.name, {
                isGlobal: assistant.is_global === true,
              });
            }

            if (!existingId) {
              throw createError;
            }

            logger.info(`  Found existing assistant ID: ${existingId}. Updating...`);
            const updateResponse = await client.assistants.update(existingId, apiParams);
            assertAssistantValidationSucceeded(updateResponse, 'update', assistant.name);
            assistantId = existingId;
            logger.info(`✓ Recovered and updated assistant: ${assistant.name} (${assistantId})`);
            stats.updated++;
          }

          stateManager.updateAssistantState(assistant.name, assistantId, promptContent, assistant, buildConfig);
          deployedAssistantId = assistantId;
        }
      } else {
        logger.info(`  Creating new assistant...`);

        if (process.env.DEBUG_API) {
          logger.debug('\n=== DEBUG: API Params ===');
          logger.debug(JSON.stringify(apiParams, null, 2));
          logger.debug('=========================\n');
        }

        let assistantId: string;
        try {
          assistantId = await createAssistantAndGetId(client, apiParams, assistant.slug);
          logger.info(`✓ Created assistant: ${assistant.name} (${assistantId})`);
          stats.created++;
        } catch (createError) {
          if (!shouldRecoverAssistantCreateError(createError)) {
            throw createError;
          }
          logger.warn(`  ⚠️  Assistant create failed. Checking if it already exists on platform...`);

          let existingId: string | null = null;

          if (assistant.slug) {
            try {
              const existingBySlug = await client.assistants.getBySlug(assistant.slug);
              existingId = existingBySlug?.id || null;
            } catch {
              // Fall back to name lookup below
            }
          }

          if (!existingId) {
            existingId = await findAssistantByName(client, assistant.name, {
              isGlobal: assistant.is_global === true,
            });
          }

          if (!existingId) {
            throw createError;
          }

          logger.info(`  Found existing assistant ID: ${existingId}. Updating...`);
          const updateResponse = await client.assistants.update(existingId, apiParams);
          assertAssistantValidationSucceeded(updateResponse, 'update', assistant.name);
          assistantId = existingId;
          logger.info(`✓ Recovered and updated assistant: ${assistant.name} (${assistantId})`);
          stats.updated++;
        }

        stateManager.updateAssistantState(assistant.name, assistantId, promptContent, assistant, buildConfig);
        deployedAssistantId = assistantId;
      }

      if (deployedAssistantId && assistant.skills !== undefined) {
        await syncAssistantSkills(client, deployedAssistantId, resolvedSkillIds);
      }

      logger.info('');
    } catch (error) {
      logger.error(`  ❌ Failed to deploy ${assistant.name}:`);
      logApiErrorDetails(error);
      logger.info('');
      stats.failed++;
    }
  }

  return stats;
}

/** Create payload rule: include `companion_files` only when the skill currently has files. */
function companionFilesForCreate(
  companionFiles: CompanionFile[]
): { companion_files: CompanionFile[] } | Record<string, never> {
  return companionFiles.length > 0 ? { companion_files: companionFiles } : {};
}

/**
 * True when the local state entry can say what companion files the platform holds. An absent entry
 * (recover-by-name path) and an entry written before companion hashes existed both say nothing — an
 * empty `companionFileHashes` object, on the other hand, is a recorded "no companion files".
 */
function stateKnowsCompanionFiles(existingState: SkillState | undefined): boolean {
  return existingState?.companionFileHashes !== undefined;
}

/**
 * Update payload rule: send the full list when there are files now; send `[]` when the working tree
 * has none and the platform does have some (the only way to clear them); otherwise omit the field
 * entirely (SDK contract: omitted/null means unchanged).
 *
 * What the platform holds comes from state when state knows, and from
 * `skills.listCompanionFiles` when it does not — without that lookup a skill recovered by name, or
 * one whose state entry predates companion hashes, would silently keep its stale companions.
 *
 * That lookup is best-effort: a timeout, a server error, or a platform with no companion-files
 * endpoint at all warns and omits the field, leaving the platform's companions untouched rather
 * than failing an update that has nothing to do with companion files.
 */
async function companionFilesForUpdate(
  client: Awaited<ReturnType<typeof createClient>>,
  skillId: string,
  skillName: string,
  companionFiles: CompanionFile[],
  existingState: SkillState | undefined
): Promise<{ companion_files: CompanionFile[] } | Record<string, never>> {
  if (companionFiles.length > 0) {
    return { companion_files: companionFiles };
  }

  if (stateKnowsCompanionFiles(existingState)) {
    return stateHasCompanionFiles(existingState) ? { companion_files: [] } : {};
  }

  let platformCompanionFiles: Awaited<ReturnType<typeof client.skills.listCompanionFiles>>;
  try {
    platformCompanionFiles = await withTimeout(
      client.skills.listCompanionFiles(skillId),
      TIMEOUTS_MS.SKILL_FETCH,
      `Timeout listing companion files for skill "${skillId}"`
    );
  } catch (error) {
    logger.warn(
      `  ⚠️  Could not list companion files for skill "${skillName}": ` +
        `${error instanceof Error ? error.message : String(error)}. ` +
        `Leaving any companion files on the platform untouched.`
    );
    return {};
  }

  return platformCompanionFiles.length > 0 ? { companion_files: [] } : {};
}

/**
 * Deploy all skills from configuration
 * Skills must be deployed before assistants so skill_ids can be resolved
 */
// eslint-disable-next-line max-lines-per-function
export async function deploySkills(
  config: ReturnType<CodemieConfigLoader['loadConfig']>,
  client: Awaited<ReturnType<typeof createClient>>,
  loader: CodemieConfigLoader,
  stateManager: StateManager,
  rootDir: string = process.cwd()
): Promise<DeploymentStats> {
  const stats: DeploymentStats = { created: 0, updated: 0, unchanged: 0, failed: 0 };

  logger.info('🎯 Processing skills...\n');
  if (!config.resources.skills) {
    return stats;
  }

  const skillIndex = new SkillNameIndex(client);

  for (const skill of config.resources.skills) {
    try {
      logger.info(`Processing: ${skill.name}`);

      const content = loader.resolveSkillContent(skill);
      const contentChecksum = calculateChecksum(content);
      const configChecksum = calculateSkillConfigChecksum(skill);
      const visibility = (skill.visibility ?? 'project') as SkillVisibility;

      const companionFiles = hasCompanionFileLayout(skill)
        ? collectCompanionFiles(path.dirname(path.join(rootDir, skill.file as string)))
        : [];
      const { companionFilesChecksum } = calculateCompanionFilesChecksum(companionFiles);

      const existingState = stateManager.getSkillState(skill.name);

      if (existingState) {
        const existsOnPlatform = await checkSkillExists(client, skill.name, stateManager);

        if (existsOnPlatform) {
          const companionFilesChanged =
            companionFiles.length > 0 || stateHasCompanionFiles(existingState)
              ? existingState.companionFilesChecksum !== companionFilesChecksum
              : false;
          const hasChanged =
            existingState.contentChecksum !== contentChecksum ||
            existingState.configChecksum !== configChecksum ||
            companionFilesChanged;

          if (hasChanged) {
            logger.info(`  Updating skill (ID: ${existingState.id})...`);

            if (process.env.DEBUG_API) {
              logger.debug('\n=== DEBUG: Update API Params ===');
              logger.debug(
                JSON.stringify(
                  { name: skill.name, description: skill.description, categories: skill.categories },
                  null,
                  2
                )
              );
              logger.debug('================================\n');
            }

            await client.skills.update(existingState.id, {
              name: skill.name,
              description: skill.description,
              content,
              visibility,
              categories: skill.categories,
              ...(await companionFilesForUpdate(client, existingState.id, skill.name, companionFiles, existingState)),
            });
            logger.info(`✓ Updated skill: ${skill.name} (${existingState.id})`);

            stateManager.updateSkillState(skill.name, existingState.id, content, skill, companionFiles);

            stats.updated++;
          } else {
            logger.info(`  ✓ No changes detected (ID: ${existingState.id})`);
            stats.unchanged++;
          }
        } else {
          logger.info(`  ⚠️  Skill ID from state not found on platform, will create new`);
          logger.info(`  Creating new skill...`);

          const result = await client.skills.create({
            name: skill.name,
            description: skill.description,
            content,
            project: config.project.name,
            visibility,
            categories: skill.categories,
            ...companionFilesForCreate(companionFiles),
          });

          logger.info(`✓ Created skill: ${skill.name} (${result.id})`);
          skillIndex.record(skill.name, result.id);

          stateManager.updateSkillState(skill.name, result.id, content, skill, companionFiles);

          stats.created++;
        }
      } else {
        logger.info(`  Creating new skill...`);

        if (process.env.DEBUG_API) {
          logger.debug('\n=== DEBUG: API Params ===');
          logger.debug(
            JSON.stringify(
              { name: skill.name, description: skill.description, visibility, categories: skill.categories },
              null,
              2
            )
          );
          logger.debug('=========================\n');
        }

        let skillId: string;
        try {
          const result = await client.skills.create({
            name: skill.name,
            description: skill.description,
            content,
            project: config.project.name,
            visibility,
            categories: skill.categories,
            ...companionFilesForCreate(companionFiles),
          });
          skillId = result.id;
          logger.info(`✓ Created skill: ${skill.name} (${skillId})`);
          skillIndex.record(skill.name, skillId);
          stats.created++;
        } catch (createError) {
          const msg = createError instanceof Error ? createError.message : String(createError);
          if (!msg.includes('already exists')) {
            throw createError;
          }
          // Skill already exists on platform but not in local state (e.g., from a previous partial run).
          // Recover by looking up the existing skill and updating it.
          logger.warn(`  ⚠️  Skill already exists on platform (no local state). Fetching ID to recover...`);
          const existingId = await findSkillByName(skillIndex, skill.name);
          if (!existingId) {
            throw new Error(`Skill "${skill.name}" reported as existing but could not be found by name.`);
          }
          logger.info(`  Found existing skill ID: ${existingId}. Updating...`);
          await client.skills.update(existingId, {
            name: skill.name,
            description: skill.description,
            content,
            visibility,
            categories: skill.categories,
            ...(await companionFilesForUpdate(client, existingId, skill.name, companionFiles, undefined)),
          });
          skillId = existingId;
          logger.info(`✓ Recovered and updated skill: ${skill.name} (${skillId})`);
          stats.updated++;
        }

        stateManager.updateSkillState(skill.name, skillId, content, skill, companionFiles);
      }

      logger.info('');
    } catch (error) {
      logger.error(`  ❌ Failed to deploy ${skill.name}:`);
      logApiErrorDetails(error);
      logger.info('');
      stats.failed++;
    }
  }

  return stats;
}

/**
 * Helper: Create datasource and retrieve its ID
 */
async function createDatasourceAndGetId(
  client: Awaited<ReturnType<typeof createClient>>,
  createParams: DataSourceCreateParams,
  datasourceName: string
): Promise<string> {
  await client.datasources.create(createParams);
  logger.info(`✓ Created datasource: ${datasourceName}`);

  logger.info(`  Fetching datasource ID...`);
  const datasourceId = await findDatasourceByName(client, datasourceName);

  if (!datasourceId) {
    throw new Error(`Datasource created but not found by name: ${datasourceName}`);
  }

  logger.info(`  Found ID: ${datasourceId}`);
  return datasourceId;
}

/**
 * Helper: Create datasource, recovering gracefully if the datasource already
 * exists on the platform (i.e. the "Index already exists" error). In that case
 * we look up the existing datasource by name and return its ID so state is
 * synced, rather than failing the whole deployment.
 */
async function createOrRecoverDatasource(
  client: Awaited<ReturnType<typeof createClient>>,
  createParams: DataSourceCreateParams,
  datasourceName: string
): Promise<string> {
  try {
    return await createDatasourceAndGetId(client, createParams, datasourceName);
  } catch (createError) {
    if (createError instanceof Error && createError.message.toLowerCase().includes('already exists')) {
      logger.warn(`  ⚠️  Datasource "${datasourceName}" already exists on platform. Recovering existing ID...`);
      const existingId = await findDatasourceByName(client, datasourceName);
      if (!existingId) {
        throw new Error(
          `Datasource "${datasourceName}" already exists but could not be found by name. Manual intervention required.`
        );
      }
      logger.info(`  Found existing ID: ${existingId}`);
      return existingId;
    }
    throw createError;
  }
}

/**
 * Deploy all datasources from configuration
 * Extracted from main() for better maintainability
 */
// eslint-disable-next-line max-lines-per-function
export async function deployDatasources(
  config: ReturnType<CodemieConfigLoader['loadConfig']>,
  client: Awaited<ReturnType<typeof createClient>>,
  stateManager: StateManager
): Promise<DeploymentStats> {
  const stats: DeploymentStats = { created: 0, updated: 0, unchanged: 0, failed: 0 };

  logger.info('📊 Processing datasources...\n');
  if (!config.resources.datasources) {
    return stats;
  }

  for (const datasource of config.resources.datasources) {
    try {
      logger.info(`Processing: ${datasource.name}`);

      const configChecksum = calculateDatasourceConfigChecksum(datasource);

      const createParams = datasourceResourceToCreateParams(datasource, config.project.name);

      const existingState = stateManager.getDatasourceState(datasource.name);

      if (existingState) {
        // Use shared logic for existence check (same as preview.ts)
        const existsOnPlatform = await checkDatasourceExists(client, datasource.name, stateManager);

        if (existsOnPlatform) {
          const hasChanged = existingState.configChecksum !== configChecksum;

          // Force reindex if flag is set, even if unchanged
          if (hasChanged || datasource.force_reindex) {
            if (datasource.force_reindex && !hasChanged) {
              logger.info(`  Force reindexing datasource (ID: ${existingState.id})...`);
            } else {
              logger.info(`  Updating datasource (ID: ${existingState.id})...`);
            }

            // Add full_reindex flag if force_reindex is enabled
            const updateParams: DataSourceUpdateParams = {
              ...createParams,
              ...(datasource.force_reindex && { full_reindex: true }),
            };

            try {
              await client.datasources.update(updateParams);
              logger.info(
                `✓ ${datasource.force_reindex && !hasChanged ? 'Reindexed' : 'Updated'} datasource: ${datasource.name} (${existingState.id})`
              );
              stateManager.updateDatasourceState(datasource.name, existingState.id, datasource);
              stats.updated++;
            } catch (updateError) {
              if (updateError instanceof Error && updateError.message.includes('unknown not found')) {
                logger.warn(
                  `  ⚠️  Datasource "${datasource.name}" update returned 404 — likely externally managed and read-only. Skipping update.`
                );
                // Sync checksum so future deploys skip this datasource unless its config changes
                stateManager.updateDatasourceState(datasource.name, existingState.id, datasource);
                stats.unchanged++;
              } else {
                throw updateError;
              }
            }
          } else {
            logger.info(`  ✓ No changes detected (ID: ${existingState.id})`);
            stats.unchanged++;
          }
        } else {
          logger.info(`  ⚠️  Datasource ID from state not found on platform, will create new`);
          logger.info(`  Creating new datasource...`);
          const datasourceId = await createOrRecoverDatasource(client, createParams, datasource.name);
          stateManager.updateDatasourceState(datasource.name, datasourceId, datasource);
          stats.created++;
        }
      } else {
        logger.info(`  Creating new datasource...`);
        const datasourceId = await createOrRecoverDatasource(client, createParams, datasource.name);
        stateManager.updateDatasourceState(datasource.name, datasourceId, datasource);
        stats.created++;
      }

      logger.info('');
    } catch (error) {
      logger.error(`  ❌ Failed to deploy ${datasource.name}:`);
      logApiErrorDetails(error);
      logger.info('');
      stats.failed++;
    }
  }

  return stats;
}

/**
 * Deploy all workflows from configuration
 * Extracted from main() for better maintainability
 */
// eslint-disable-next-line max-lines-per-function
export async function deployWorkflows(
  config: ReturnType<CodemieConfigLoader['loadConfig']>,
  client: Awaited<ReturnType<typeof createClient>>,
  stateManager: StateManager,
  rootDir: string = process.cwd()
): Promise<DeploymentStats> {
  const stats: DeploymentStats = { created: 0, updated: 0, unchanged: 0, failed: 0 };

  logger.info('🔄 Processing workflows...\n');
  if (!config.resources.workflows) {
    return stats;
  }

  for (const workflow of config.resources.workflows) {
    try {
      logger.info(`Processing: ${workflow.name}`);

      const yamlPath = path.join(rootDir, workflow.definition);
      if (!fs.existsSync(yamlPath)) {
        throw new Error(`Workflow definition file not found: ${workflow.definition}`);
      }
      const yamlConfigContent = fs.readFileSync(yamlPath, 'utf8');

      const workflowYaml = yaml.parse(yamlConfigContent) as WorkflowYaml;

      // Resolve assistant_name → assistant_id (using state.json)
      const referencesToResolve: Array<{ localId: string; reference: string; uuid: string }> = [];

      for (const assistant of workflowYaml.assistants ?? []) {
        // Skip inline assistants (defined in-place with model + system_prompt, NO assistant_name)
        // If has assistant_name, it's a REFERENCE even if model/system_prompt are present (they're overrides)
        const isInline = !assistant.assistant_name && assistant.model && assistant.system_prompt;
        if (isInline) {
          logger.info(`  Skipping inline assistant: ${assistant.id}`);
          continue;
        }

        if (!assistant.assistant_id) {
          let resolvedId: string | undefined;

          if (assistant.assistant_name) {
            // Resolve by NAME from state.json
            const assistantState = stateManager.getAssistantState(assistant.assistant_name);
            if (assistantState) {
              resolvedId = assistantState.id;
              logger.info(`  Resolved (name): ${assistant.assistant_name} → ${resolvedId.slice(0, 8)}...`);
            } else {
              // Fallback: check imported.assistants
              const importedAssistant = config.imported?.assistants?.find(
                (a: ImportedResource) => a.name === assistant.assistant_name
              );
              if (importedAssistant && importedAssistant.id) {
                resolvedId = importedAssistant.id;
                logger.info(`  Resolved (imported): ${assistant.assistant_name} → ${resolvedId.slice(0, 8)}...`);
              } else {
                throw new Error(
                  `Assistant "${assistant.assistant_name}" not found in state or imported. ` +
                    `Ensure the assistant is deployed first or added to imported.assistants.`
                );
              }
            }
          } else {
            throw new Error(`Workflow assistant reference must have 'assistant_name' (local id: ${assistant.id})`);
          }

          assistant.assistant_id = resolvedId;

          const referenceName = assistant.assistant_name;

          delete assistant.assistant_name;

          referencesToResolve.push({
            localId: assistant.id,
            reference: referenceName || assistant.id,
            uuid: resolvedId,
          });
        }
      }

      const yamlConfig = yaml.stringify(workflowYaml);

      const workflowYamlChecksum = calculateChecksum(yamlConfigContent);
      const configChecksum = calculateWorkflowConfigChecksum(workflow);

      const existingState = stateManager.getWorkflowState(workflow.name);

      // Use shared logic for existence check (same as preview.ts)
      const existsOnPlatform = existingState ? await checkWorkflowExists(client, workflow.name, stateManager) : false;

      if (existingState && existsOnPlatform) {
        const hasChanged =
          existingState.workflowYamlChecksum !== workflowYamlChecksum ||
          existingState.configChecksum !== configChecksum;

        if (hasChanged) {
          const apiParams = {
            project: config.project.name,
            name: workflow.name,
            description: workflow.description,
            yaml_config: yamlConfig,
            mode: workflow.mode,
            shared: workflow.shared,
            icon_url: workflow.icon_url,
          };

          if (process.env.DEBUG_API) {
            logger.debug('\n=== DEBUG: API Params ===');
            logger.debug(JSON.stringify(apiParams, null, 2));
            logger.debug('=========================\n');
          }

          logger.info(`  Updating workflow (ID: ${existingState.id})...`);

          await client.workflows.update(existingState.id, apiParams);

          logger.info(`✓ Updated workflow: ${workflow.name} (${existingState.id})`);

          stateManager.updateWorkflowState(workflow.name, existingState.id, workflowYamlChecksum, configChecksum);

          stats.updated++;
        } else {
          logger.info(`  ✓ No changes detected (ID: ${existingState.id})`);
          stats.unchanged++;
        }
      } else {
        if (existingState) {
          logger.info(`  ⚠️  Workflow ID from state not found on platform, looking for a same-name workflow`);
        }

        const apiParams = {
          project: config.project.name,
          name: workflow.name,
          description: workflow.description,
          yaml_config: yamlConfig,
          mode: workflow.mode || 'Sequential',
          shared: workflow.shared ?? true,
          icon_url: workflow.icon_url,
        };

        if (process.env.DEBUG_API) {
          logger.debug('\n=== DEBUG: API Params ===');
          logger.debug(JSON.stringify(apiParams, null, 2));
          logger.debug('=========================\n');
        }

        const foundId = await findWorkflowByName(client, workflow.name, config.project.name);

        if (foundId) {
          await client.workflows.update(foundId, apiParams);

          logger.info(`✓ Adopted existing workflow ${workflow.name} (${foundId})`);

          stateManager.updateWorkflowState(workflow.name, foundId, workflowYamlChecksum, configChecksum);

          stats.updated++;
        } else {
          logger.info(`  Creating new workflow...`);

          const result = await client.workflows.create(apiParams);

          const workflowId = (result.data as { id: string })?.id || (result as { id: string }).id;
          if (!workflowId) {
            throw new Error('Workflow created but ID not returned');
          }

          logger.info(`✓ Created workflow: ${workflow.name} (${workflowId})`);

          stateManager.updateWorkflowState(workflow.name, workflowId, workflowYamlChecksum, configChecksum);

          stats.created++;
        }
      }

      logger.info('');
    } catch (error) {
      logger.error(`  ❌ Failed to deploy ${workflow.name}:`);
      logApiErrorDetails(error);
      logger.info('');
      stats.failed++;
    }
  }

  return stats;
}

/** Platform-side "this skill or attachment is already gone" responses, tolerated the way syncAssistantSkills does. */
function isAlreadyGoneError(error: unknown): boolean {
  const message = (error instanceof Error ? error.message : String(error)).toLowerCase();
  return message.includes('404') || message.includes('not found') || message.includes('not attached');
}

/**
 * Detach every skill of the group being replaced from every assistant that could hold it, so the
 * delete below cannot leave dangling attachments. Runs before the first delete: a detach error aborts
 * the run while the skills still exist on the platform.
 */
async function detachSkillsBeforeDelete(
  client: Awaited<ReturnType<typeof createClient>>,
  assistantIds: string[],
  skills: Array<{ name: string; id: string }>,
  group: string
): Promise<void> {
  if (skills.length === 0 || assistantIds.length === 0) {
    return;
  }

  const targetIds = new Set(skills.map((skill) => skill.id));
  logger.info(`🔗 Detaching ${skills.length} skill(s) from ${assistantIds.length} assistant(s)...`);

  for (const assistantId of assistantIds) {
    let attachedTargetIds: string[];
    try {
      const currentSkills = await client.skills.getAssistantSkills(assistantId);
      attachedTargetIds = currentSkills.map((skill) => skill.id).filter((id) => targetIds.has(id));
    } catch (fetchError) {
      logger.warn(`  ⚠️  Could not list skills of assistant ${assistantId}, attempting every detach instead`);
      logger.debug(`     ${fetchError instanceof Error ? fetchError.message : String(fetchError)}`);
      attachedTargetIds = [...targetIds];
    }

    for (const skillId of attachedTargetIds) {
      try {
        await client.skills.detachFromAssistant(assistantId, skillId);
        logger.info(`    ✓ Detached skill ${skillId} from assistant ${assistantId}`);
      } catch (detachError) {
        if (isAlreadyGoneError(detachError)) {
          logger.info(`    ✓ Skill ${skillId} already detached from assistant ${assistantId}`);
          continue;
        }
        const message = detachError instanceof Error ? detachError.message : String(detachError);
        throw new Error(
          `Failed to detach skill ${skillId} from assistant ${assistantId} while replacing skill group "${group}": ` +
            `${message}. Nothing was deleted.`
        );
      }
    }
  }

  logger.info('');
}

/**
 * Delete the selected skills and drop their state entries. The first hard failure aborts the whole
 * replacement, before any skill is recreated.
 */
async function deleteSkillsForReplacement(
  client: Awaited<ReturnType<typeof createClient>>,
  stateManager: StateManager,
  skills: Array<{ name: string; id: string }>,
  group: string
): Promise<number> {
  let deleted = 0;

  for (const { name, id } of skills) {
    try {
      await client.skills.delete(id);
      logger.info(`  🗑️  Deleted skill: ${name} (${id})`);
      deleted++;
    } catch (deleteError) {
      if (isAlreadyGoneError(deleteError)) {
        logger.warn(`  ⚠️  Skill ${name} (${id}) not found on platform (already deleted) - removing from state`);
      } else {
        const message = deleteError instanceof Error ? deleteError.message : String(deleteError);
        throw new Error(
          `Failed to delete skill "${name}" (${id}) while replacing skill group "${group}": ${message}. ` +
            `No skills were recreated; rerun the command once the platform error is resolved.`
        );
      }
    }

    stateManager.deleteSkillState(name);
  }

  logger.info('');
  return deleted;
}

/**
 * Force-recreate a labelled group of skills: detach, delete, then deploy only that group's skills and
 * the assistants referencing them (with their sub-assistants, so the dependency sort still resolves).
 * Datasources and workflows are not touched. Recreated skills get brand new platform ids.
 */
export async function replaceSkillGroupResources(
  config: ReturnType<CodemieConfigLoader['loadConfig']>,
  client: Awaited<ReturnType<typeof createClient>>,
  loader: CodemieConfigLoader,
  stateManager: StateManager,
  group: string,
  rootDir: string = process.cwd()
): Promise<{ stats: DeploymentStats; deleted: number }> {
  const { namesToDelete, groupSkills } = selectSkillGroupForReplacement(config, stateManager, group);

  logger.info(`♻️  Replacing skill group "${group}"...\n`);
  logger.info(`   ${namesToDelete.length} skill(s) to delete, ${groupSkills.length} skill(s) to recreate\n`);

  const skillsToDelete = namesToDelete
    .map((name) => ({ name, id: stateManager.getIdByName('skill', name) }))
    .filter((entry): entry is { name: string; id: string } => Boolean(entry.id));

  await detachSkillsBeforeDelete(client, collectAssistantIdsForDetach(stateManager, config), skillsToDelete, group);
  const deleted = await deleteSkillsForReplacement(client, stateManager, skillsToDelete, group);

  // Narrowed only by what gets DEPLOYED: `datasources` stays intact because `deployAssistants`
  // resolves `datasource_names` out of it (plus `imported.datasources`) and throws when a name is
  // missing. Neither `deployDatasources` nor `deployWorkflows` is called from this path, so keeping
  // the lists deploys nothing — emptying them only breaks name resolution.
  const skillStats = await deploySkills(
    {
      ...config,
      resources: { ...config.resources, skills: groupSkills, assistants: [], workflows: [] },
    },
    client,
    loader,
    stateManager,
    rootDir
  );

  const referencingAssistants = expandAssistantsWithDependencies(
    filterAssistantsReferencingSkillGroup(config.resources.assistants, config.resources.skills, group),
    config.resources.assistants
  );
  logger.info(`   ${referencingAssistants.length} assistant(s) reference the replaced skill group\n`);

  const assistantStats = await deployAssistants(
    {
      ...config,
      resources: { ...config.resources, assistants: referencingAssistants, workflows: [] },
    },
    client,
    loader,
    stateManager
  );

  return {
    deleted,
    stats: {
      created: skillStats.created + assistantStats.created,
      updated: skillStats.updated + assistantStats.updated,
      unchanged: skillStats.unchanged + assistantStats.unchanged,
      failed: skillStats.failed + assistantStats.failed,
    },
  };
}

function logDeploymentSummary(stats: DeploymentStats, deleted: number): void {
  logger.info('='.repeat(50));
  logger.info('📊 Deployment Summary:\n');
  logger.info(`  ✅ Created: ${stats.created}`);
  logger.info(`  🔄 Updated: ${stats.updated}`);
  logger.info(`  📋 Unchanged: ${stats.unchanged}`);
  if (deleted > 0) {
    logger.info(`  🗑️  Deleted: ${deleted}`);
  }
  if (stats.failed > 0) {
    logger.info(`  ❌ Failed: ${stats.failed}`);
  }
  logger.info('');
}

// eslint-disable-next-line max-lines-per-function
export async function deployResources(options: {
  appConfig: AppConfig;
  prune?: boolean;
  skipDatasources?: boolean;
  replaceSkillGroup?: string;
  yesReplaceSkills?: boolean;
}): Promise<void> {
  logger.info('🚀 Deploying resources to Codemie...\n');

  try {
    const { appConfig, prune = false, skipDatasources = false, replaceSkillGroup, yesReplaceSkills = false } = options;

    if (replaceSkillGroup && !yesReplaceSkills) {
      throw new Error(
        `Refusing to replace skill group "${replaceSkillGroup}" without --yes-replace-skills. ` +
          `Replacing a group deletes its skills and recreates them with new ids; nothing was touched.`
      );
    }

    const loader = new CodemieConfigLoader(appConfig);
    const stateManager = new StateManager(appConfig);

    logger.info('📄 Loading configuration...');
    const config = loader.loadConfig();
    logger.info(`✓ Loaded config for project: ${config.project.name}\n`);

    const skillDescriptionErrors = validateSkillDescriptions(config.resources.skills ?? []);
    if (skillDescriptionErrors.length > 0) {
      throw new Error(skillDescriptionErrors.join('\n'));
    }

    logger.info('🔌 Connecting to Codemie API...');
    const client = await createClient(config);
    logger.info('✓ Connected to Codemie API\n');

    if (replaceSkillGroup) {
      if (prune) {
        logger.info('⚠️  --prune is ignored with --replace-skill-group\n');
      }
      if (skipDatasources) {
        logger.info('ℹ️  Datasources are skipped by --replace-skill-group anyway\n');
      }

      const replacement = await replaceSkillGroupResources(
        config,
        client,
        loader,
        stateManager,
        replaceSkillGroup,
        appConfig.rootDir
      );

      logDeploymentSummary(replacement.stats, replacement.deleted);

      if (replacement.stats.failed > 0) {
        throw new Error('Deployment completed with errors');
      }
      logger.info('✅ Deployment successful!');
      return;
    }

    logger.info('🧹 Checking for orphaned resources...');
    const cleanupManager = new CleanupManager(client, stateManager);
    const foundOrphaned = cleanupManager.findOrphanedResources(config);
    const orphaned = skipDatasources ? { ...foundOrphaned, datasources: [] } : foundOrphaned;
    const skippedOrphanedDatasources = foundOrphaned.datasources.length - orphaned.datasources.length;
    if (skippedOrphanedDatasources > 0) {
      logger.info(`  ⏭️  ${skippedOrphanedDatasources} orphaned datasource(s) skipped (--skip-datasources)`);
    }

    const totalOrphaned =
      orphaned.assistants.length + orphaned.datasources.length + orphaned.workflows.length + orphaned.skills.length;
    let deleted = 0;

    if (totalOrphaned > 0) {
      logger.info(`\n⚠️  Found ${totalOrphaned} orphaned resource(s):`);
      if (orphaned.assistants.length > 0) {
        logger.info(`   • ${orphaned.assistants.length} assistant(s)`);
      }
      if (orphaned.datasources.length > 0) {
        logger.info(`   • ${orphaned.datasources.length} datasource(s)`);
      }
      if (orphaned.workflows.length > 0) {
        logger.info(`   • ${orphaned.workflows.length} workflow(s)`);
      }
      if (orphaned.skills.length > 0) {
        logger.info(`   • ${orphaned.skills.length} skill(s)`);
        const importedSkillNames = new Set(config.imported?.skills?.map((skill) => skill.name.toLowerCase()) || []);
        const migratedImportedSkills = orphaned.skills.filter((name) => importedSkillNames.has(name.toLowerCase()));
        if (migratedImportedSkills.length > 0) {
          logger.info(
            `     ⚠️  ${migratedImportedSkills.length} skill(s) also exist in imported.skills. ` +
              `Run with --prune to remove stale IaC-managed skill state and delete old managed skill(s) from platform.`
          );
        }
      }

      if (process.env.SAMPLE_DEPLOY === '1') {
        logger.info('\n🔎 SAMPLE_DEPLOY=1 -> Skipping orphan deletion (simulation / partial deploy mode)\n');
      } else if (prune) {
        logger.info('\n⏳ Orphaned resources will be deleted after deployment (to allow skill detachment first)\n');
      } else {
        logger.info('\n⚠️  Orphaned resources found but not deleted.');
        logger.info('   Use --prune flag to delete them.\n');
      }
    } else {
      logger.info('✓ No orphaned resources found\n');
    }

    let created = 0;
    let updated = 0;
    let unchanged = 0;
    let failed = 0;

    if (skipDatasources) {
      logger.info('📊 Processing datasources...\n');
      logger.info(`  ⏭️  Skipped (--skip-datasources): ${config.resources.datasources?.length ?? 0} datasource(s)\n`);
    } else {
      const datasourceStats = await deployDatasources(config, client, stateManager);
      created += datasourceStats.created;
      updated += datasourceStats.updated;
      unchanged += datasourceStats.unchanged;
      failed += datasourceStats.failed;
    }

    const skillStats = await deploySkills(config, client, loader, stateManager, appConfig.rootDir);
    created += skillStats.created;
    updated += skillStats.updated;
    unchanged += skillStats.unchanged;
    failed += skillStats.failed;

    const assistantStats = await deployAssistants(config, client, loader, stateManager);
    created += assistantStats.created;
    updated += assistantStats.updated;
    unchanged += assistantStats.unchanged;
    failed += assistantStats.failed;

    const workflowStats = await deployWorkflows(config, client, stateManager, appConfig.rootDir);
    created += workflowStats.created;
    updated += workflowStats.updated;
    unchanged += workflowStats.unchanged;
    failed += workflowStats.failed;

    if (totalOrphaned > 0 && prune && process.env.SAMPLE_DEPLOY !== '1') {
      logger.info('🗑️  Deleting orphaned resources (removed from config)...\n');
      const cleanupResult = await cleanupManager.deleteOrphanedResources(orphaned);
      deleted =
        cleanupResult.deleted.assistants.length +
        cleanupResult.deleted.datasources.length +
        cleanupResult.deleted.workflows.length +
        cleanupResult.deleted.skills.length;
      if (deleted > 0) {
        logger.info(`\n✓ Deleted ${deleted} orphaned resource(s)\n`);
      }
      if (cleanupResult.errors.length > 0) {
        logger.info(`\n⚠️  ${cleanupResult.errors.length} error(s) during cleanup\n`);
      }
    }

    logDeploymentSummary({ created, updated, unchanged, failed }, deleted);

    if (failed > 0) {
      throw new Error('Deployment completed with errors');
    } else {
      logger.info('✅ Deployment successful!');
    }
  } catch (error) {
    logger.error('\n❌ Deployment failed:');
    logger.error(error instanceof Error ? error.message : String(error));
    throw error;
  }
}

export async function main(options: {
  appConfig: AppConfig;
  prune?: boolean;
  skipDatasources?: boolean;
  replaceSkillGroup?: string;
  yesReplaceSkills?: boolean;
}) {
  try {
    await deployResources(options);
    process.exit(0);
  } catch (error) {
    logger.error('\n❌ Deployment failed:');
    logger.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
