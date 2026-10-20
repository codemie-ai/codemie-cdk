/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import type { CodeMieClient } from 'codemie-sdk';

import type { CodemieConfig } from '../types/codemieConfig';

import { logger } from './logger';
import type { StateManager } from './stateManager';

export interface CleanupResult {
  deleted: {
    assistants: string[];
    datasources: string[];
    workflows: string[];
    skills: string[];
  };
  errors: Array<{
    type: 'assistant' | 'datasource' | 'workflow' | 'skill';
    name: string;
    error: string;
  }>;
}

export class CleanupManager {
  constructor(
    private client: CodeMieClient,
    private stateManager: StateManager
  ) {}

  /**
   * Check if an error indicates that a resource was not found on the platform
   * Handles both proper 404 responses
   */
  private isNotFoundError(error: unknown): boolean {
    if (typeof error === 'object' && error !== null && 'statusCode' in error && typeof error.statusCode === 'number') {
      return error.statusCode === 404;
    }
    const errorMessage = error instanceof Error ? error.message : String(error);

    // Check for explicit 404 or "not found" messages
    if (errorMessage.includes('404') || errorMessage.includes('not found') || errorMessage.includes('Not Found')) {
      return true;
    }

    return false;
  }

  /**
   * Delete a resource with graceful handling for "not found" errors
   * Returns true if deleted or not found, false if other error occurred
   */
  private async deleteResourceSafely(
    resourceType: 'assistant' | 'datasource' | 'workflow' | 'skill',
    name: string,
    id: string,
    deleteFn: () => Promise<unknown>
  ): Promise<{ success: boolean; notFound: boolean }> {
    try {
      await deleteFn();
      logger.info(`  🗑️  Deleted orphaned ${resourceType}: ${name} (${id.slice(0, 8)}...)`);
      return { success: true, notFound: false };
    } catch (error) {
      if (this.isNotFoundError(error)) {
        logger.info(
          `  ⚠️  ${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)} ${name} not found on platform (already deleted) - removing from state`
        );
        return { success: true, notFound: true };
      }
      throw error; // Re-throw if it's a different error
    }
  }

  /**
   * Find orphaned resources (in state but not in config)
   * These are resources that were managed by IaC but removed from codemie.yaml
   * Returns resource NAMES, not IDs
   */
  findOrphanedResources(config: CodemieConfig): {
    assistants: string[];
    datasources: string[];
    workflows: string[];
    skills: string[];
  } {
    const managedResources = this.stateManager.getAllManagedResources();

    // Get names from current config
    const configAssistantNames = new Set((config.resources.assistants || []).map(({ name }) => name));

    const configDatasourceNames = new Set((config.resources.datasources || []).map(({ name }) => name));

    const configWorkflowNames = new Set((config.resources.workflows || []).map(({ name }) => name));

    const configSkillNames = new Set((config.resources.skills || []).map(({ name }) => name.toLowerCase()));

    // Find resources in state but not in config (orphaned)
    return {
      assistants: managedResources.assistants.filter((name) => !configAssistantNames.has(name)),
      datasources: managedResources.datasources.filter((name) => !configDatasourceNames.has(name)),
      workflows: managedResources.workflows.filter((name) => !configWorkflowNames.has(name)),
      skills: managedResources.skills.filter((name) => !configSkillNames.has(name.toLowerCase())),
    };
  }

  /**
   * Delete orphaned resources from platform
   * SAFETY: Only deletes resources that are in state.json (managed by IaC)
   * @param orphaned Object with resource NAMES (not IDs)
   */
  // eslint-disable-next-line max-lines-per-function
  async deleteOrphanedResources(orphaned: {
    assistants: string[];
    datasources: string[];
    workflows: string[];
    skills?: string[];
  }): Promise<CleanupResult> {
    const result: CleanupResult = {
      deleted: {
        assistants: [],
        datasources: [],
        workflows: [],
        skills: [],
      },
      errors: [],
    };

    // Delete assistants
    for (const name of orphaned.assistants) {
      try {
        if (!this.stateManager.isManagedResource('assistant', name)) {
          logger.info(`  ⚠️  Skipping ${name} - not in state (safety check)`);
          continue;
        }

        const id = this.stateManager.getIdByName('assistant', name);
        if (!id) {
          logger.info(`  ⚠️  Skipping ${name} - no ID in state`);
          continue;
        }

        await this.deleteResourceSafely('assistant', name, id, () => this.client.assistants.delete(id));

        this.stateManager.deleteAssistantState(name);
        result.deleted.assistants.push(name);
      } catch (error) {
        result.errors.push({
          type: 'assistant',
          name,
          error: error instanceof Error ? error.message : String(error),
        });
        logger.error(
          `  ❌ Failed to delete assistant ${name}: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    }

    // Delete datasources
    for (const name of orphaned.datasources) {
      try {
        if (!this.stateManager.isManagedResource('datasource', name)) {
          logger.info(`  ⚠️  Skipping ${name} - not in state (safety check)`);
          continue;
        }

        const id = this.stateManager.getIdByName('datasource', name);
        if (!id) {
          logger.info(`  ⚠️  Skipping ${name} - no ID in state`);
          continue;
        }

        await this.deleteResourceSafely('datasource', name, id, () => this.client.datasources.delete(id));

        this.stateManager.deleteDatasourceState(name);
        result.deleted.datasources.push(name);
      } catch (error) {
        result.errors.push({
          type: 'datasource',
          name,
          error: error instanceof Error ? error.message : String(error),
        });
        logger.error(
          `  ❌ Failed to delete datasource ${name}: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    }

    // Delete workflows
    for (const name of orphaned.workflows) {
      try {
        if (!this.stateManager.isManagedResource('workflow', name)) {
          logger.info(`  ⚠️  Skipping ${name} - not in state (safety check)`);
          continue;
        }

        const id = this.stateManager.getIdByName('workflow', name);
        if (!id) {
          logger.info(`  ⚠️  Skipping ${name} - no ID in state`);
          continue;
        }

        await this.deleteResourceSafely('workflow', name, id, () => this.client.workflows.delete(id));

        this.stateManager.deleteWorkflowState(name);
        result.deleted.workflows.push(name);
      } catch (error) {
        result.errors.push({
          type: 'workflow',
          name,
          error: error instanceof Error ? error.message : String(error),
        });
        logger.error(
          `  ❌ Failed to delete workflow ${name}: ${error instanceof Error ? error.message : String(error)}`
        );
      }
    }

    // Delete skills
    for (const name of orphaned.skills || []) {
      try {
        if (!this.stateManager.isManagedResource('skill', name)) {
          logger.info(`  ⚠️  Skipping ${name} - not in state (safety check)`);
          continue;
        }

        const id = this.stateManager.getIdByName('skill', name);
        if (!id) {
          logger.info(`  ⚠️  Skipping ${name} - no ID in state`);
          continue;
        }

        await this.deleteResourceSafely('skill', name, id, () => this.client.skills.delete(id));

        this.stateManager.deleteSkillState(name);
        result.deleted.skills.push(name);
      } catch (error) {
        result.errors.push({
          type: 'skill',
          name,
          error: error instanceof Error ? error.message : String(error),
        });
        logger.error(`  ❌ Failed to delete skill ${name}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    return result;
  }

  /**
   * Get summary of orphaned resources
   */
  getOrphanedSummary(orphaned: {
    assistants: string[];
    datasources: string[];
    workflows: string[];
    skills?: string[];
  }): string {
    const total =
      orphaned.assistants.length +
      orphaned.datasources.length +
      orphaned.workflows.length +
      (orphaned.skills?.length ?? 0);

    if (total === 0) {
      return 'No orphaned resources found';
    }

    const parts: string[] = [];
    if (orphaned.assistants.length > 0) {
      parts.push(`${orphaned.assistants.length} assistant(s)`);
    }
    if (orphaned.datasources.length > 0) {
      parts.push(`${orphaned.datasources.length} datasource(s)`);
    }
    if (orphaned.workflows.length > 0) {
      parts.push(`${orphaned.workflows.length} workflow(s)`);
    }
    if ((orphaned.skills?.length ?? 0) > 0) {
      parts.push(`${orphaned.skills!.length} skill(s)`);
    }

    return `Found ${total} orphaned resource(s): ${parts.join(', ')}`;
  }
}
