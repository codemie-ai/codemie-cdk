/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

import * as yaml from 'yaml';

import type { AppConfig } from '../appConfig';
import type { CodemieConfig, AssistantConfig, SkillResource } from '../types/codemieConfig';

import { resolveImports } from './configImports';
import { namesEqual } from './nameUtils';
import { expandSkillSourceDirs } from './skillSourceLoader';
import { validateSkillDescriptions } from './validationUtils';

export class CodemieConfigLoader {
  private readonly appConfig: AppConfig;

  constructor(appConfig: AppConfig) {
    this.appConfig = appConfig;
  }

  /**
   * Load and parse the main codemie.yaml configuration file
   */
  loadConfig(): CodemieConfig {
    const { rootDir, codemieConfig } = this.appConfig;
    const configPath = path.join(rootDir, codemieConfig);

    if (!fs.existsSync(configPath)) {
      throw new Error(`Configuration file not found: ${configPath}`);
    }

    const content = fs.readFileSync(configPath, 'utf8');
    const config = yaml.parse(content) as CodemieConfig;

    // Resolve $import directives recursively
    resolveImports(config, rootDir);

    // Substitute environment variables
    this.substituteEnvVars(config);

    // Expand skill source_dir entries into flat skill resources
    if (config.resources.skills) {
      config.resources.skills = expandSkillSourceDirs(config.resources.skills, rootDir);
    }

    // Apply datasource defaults
    this.applyDatasourceDefaults(config);

    // Global resolution of all $ref references (universal approach)
    // This handles all references uniformly: integrations, tool definitions, etc.
    this.resolveReferencesRecursive(config, config);

    // Validate datasource setting_id fields (must be strings, not objects)
    this.validateDatasourceIntegrationReferences(config);

    return config;
  }

  /**
   * Load assistant prompt file
   */
  loadPrompt(promptPath: string): string {
    const { rootDir } = this.appConfig;
    const fullPath = path.join(rootDir, promptPath);

    if (!fs.existsSync(fullPath)) {
      throw new Error(`Prompt file not found: ${fullPath}`);
    }

    return fs.readFileSync(fullPath, 'utf8');
  }

  /**
   * Load skill content file (.skill.md)
   */
  loadSkillContent(contentPath: string): string {
    const { rootDir } = this.appConfig;
    const fullPath = path.join(rootDir, contentPath);

    if (!fs.existsSync(fullPath)) {
      throw new Error(`Skill content file not found: ${fullPath}`);
    }

    return fs.readFileSync(fullPath, 'utf8');
  }

  /**
   * Resolve a skill's content: prefers an already-loaded `content` (e.g. from an expanded
   * `source_dir` entry) and otherwise falls back to reading `file`. This is the single
   * content accessor for skills — every consumer routes through it.
   */
  resolveSkillContent(skill: SkillResource): string {
    if (skill.content !== undefined) {
      return skill.content;
    }

    if (skill.file) {
      return this.loadSkillContent(skill.file);
    }

    throw new Error(`Skill "${skill.name}" has neither 'content' nor 'file' to load content from`);
  }

  /**
   * Load assistant configuration file
   */
  loadAssistantConfig(configPath: string): AssistantConfig {
    const { rootDir } = this.appConfig;
    const fullPath = path.join(rootDir, configPath);

    if (!fs.existsSync(fullPath)) {
      throw new Error(`Config file not found: ${fullPath}`);
    }

    const content = fs.readFileSync(fullPath, 'utf8');
    return yaml.parse(content) as AssistantConfig;
  }

  /**
   * Validate that all referenced files exist
   */
  validateFiles(config: CodemieConfig): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    const { rootDir } = this.appConfig;

    // Validate assistant files
    if (config.resources.assistants) {
      for (const assistant of config.resources.assistants) {
        if (!assistant.prompt) {
          errors.push(`Missing 'prompt' for assistant: ${assistant.name}`);
        } else if (!fs.existsSync(path.join(rootDir, assistant.prompt))) {
          errors.push(`Prompt file not found for ${assistant.name}: ${assistant.prompt}`);
        }

        // Config is optional
        if (assistant.config) {
          const configPath = path.join(rootDir, assistant.config);
          if (!fs.existsSync(configPath)) {
            errors.push(`Config file not found for ${assistant.name}: ${assistant.config}`);
          }
        }

        // Validate required runtime settings
        if (!assistant.description) {
          errors.push(`Missing 'description' for assistant: ${assistant.name}`);
        }
        if (!assistant.model) {
          errors.push(`Missing 'model' for assistant: ${assistant.name}`);
        }
        // Slug is optional (platform generates if not provided)
      }
    }

    // Validate skill files: at least one of 'file' or 'content' is required. Both together is
    // the normal shape of a `source_dir`-expanded skill — `content` is the body deploy/preview/
    // backup use and `file` points at the SKILL.md it came from, for error messages.
    if (config.resources.skills) {
      for (const skill of config.resources.skills) {
        const hasFile = !!skill.file;
        const hasContent = skill.content !== undefined;

        if (!hasFile && !hasContent) {
          errors.push(`Skill '${skill.name}' must specify at least one of 'file' or 'content'`);
        }

        if (hasFile && !fs.existsSync(path.join(rootDir, skill.file as string))) {
          errors.push(`Content file not found for skill ${skill.name}: ${skill.file}`);
        }
      }

      errors.push(...validateSkillDescriptions(config.resources.skills));
    }

    for (const skill of config.imported?.skills || []) {
      if (!skill.name) {
        errors.push('Imported skill entry is missing required field: name');
      }
      if (!skill.id) {
        errors.push(`Imported skill "${skill.name || '<unknown>'}" is missing required field: id`);
      }
    }

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  /**
   * Recursively resolve all $ref in an object/array structure
   * Handles both object references { $ref: "path" } and string references "$ref:path"
   *
   * @param current - Current node being processed (starts with root config, then recurses into children)
   * @param rootConfig - Root config object (constant reference for resolving paths like "imported.integrations.xxx")
   * @param path - Current path in config tree (for error messages, e.g., "resources.assistants[0].toolkits")
   */
  private resolveReferencesRecursive(current: unknown, rootConfig: CodemieConfig, path: string = ''): void {
    if (!current || typeof current !== 'object') {
      return;
    }

    // Handle arrays - need to resolve $ref items that point to arrays and flatten them
    if (Array.isArray(current)) {
      this.resolveArrayReferences(current, rootConfig, path);
      return;
    }

    // Handle objects with $ref
    if ('$ref' in current && typeof current.$ref === 'string') {
      this.resolveObjectReference(current, rootConfig, path);
      return;
    }

    // Recurse into object properties and resolve "$ref:path" strings
    this.resolveObjectProperties(current as Record<string, unknown>, rootConfig, path);
  }

  /**
   * Resolve $ref items in arrays and flatten if they point to arrays
   * Example: [{ $ref: "context_definitions.repos" }] where repos is [item1, item2]
   * becomes [item1, item2]
   */
  private resolveArrayReferences(arr: unknown[], rootConfig: CodemieConfig, path: string): void {
    const result = arr.flatMap((item, i) => {
      const contextPath = `${path}[${i}]`;

      if (!this.isRefObject(item) || item.$ref.startsWith('#')) {
        this.resolveReferencesRecursive(item, rootConfig, contextPath);
        return [item];
      }

      const resolved = this.resolveReference<unknown>(rootConfig, item.$ref, contextPath);

      if (Array.isArray(resolved)) {
        return structuredClone<unknown[]>(resolved);
      }

      this.resolveObjectReference(item, rootConfig, contextPath);
      return [item];
    });

    arr.splice(0, arr.length, ...result);
  }

  /**
   * Resolve object reference: { $ref: "path" }
   * Replaces object with resolved data (in-place mutation)
   */
  private resolveObjectReference(current: Record<string, unknown>, rootConfig: CodemieConfig, path: string): void {
    const refPath = current.$ref as string;
    const contextPath = path || 'root';

    // Skip internal OpenAPI refs (e.g., "#/components/schemas/...")
    if (refPath.startsWith('#')) {
      return;
    }

    const resolved = this.resolveReference<Record<string, unknown>>(rootConfig, refPath, contextPath);

    // Replace the $ref object with resolved data
    const filteredResolved = Object.fromEntries(Object.entries(resolved).filter(([, value]) => value !== undefined));

    // Clear all existing properties and assign new ones
    for (const key of Object.keys(current)) {
      delete current[key];
    }
    Object.assign(current, filteredResolved);

    // Continue resolving in the newly resolved object
    this.resolveReferencesRecursive(current, rootConfig, path);
  }

  /**
   * Resolve object properties recursively
   * Handles both nested objects and "$ref:path" string references
   */
  private resolveObjectProperties(current: Record<string, unknown>, rootConfig: CodemieConfig, path: string): void {
    for (const [key, value] of Object.entries(current)) {
      // Handle string references like "$ref:imported.integrations.git_conn.id"
      if (typeof value === 'string' && value.startsWith('$ref:')) {
        const refPath = value.slice(5); // Remove "$ref:" prefix

        // Skip internal OpenAPI refs (e.g., "#/components/schemas/...")
        if (refPath.startsWith('#')) {
          continue;
        }

        const contextPath = path ? `${path}.${key}` : key;
        const resolved = this.resolveReference(rootConfig, refPath, contextPath);
        current[key] = resolved;
      } else {
        this.resolveReferencesRecursive(value, rootConfig, path ? `${path}.${key}` : key);
      }
    }
  }

  /**
   * Validate that datasource setting_id fields are strings (not objects)
   * For datasources, setting_id must reference a string UUID, not an integration object
   * Users should use .id suffix: $ref:imported.integrations.git_conn.id
   */
  private validateDatasourceIntegrationReferences(config: CodemieConfig): void {
    if (!config.resources.datasources) {
      return;
    }

    for (const datasource of config.resources.datasources) {
      if (datasource.setting_id && typeof datasource.setting_id !== 'string') {
        throw new TypeError(
          `Datasource "${datasource.name}" setting_id must point to a string UUID value, ` +
            `but resolved to an object. Add ".id" suffix to reference the integration ID. ` +
            `Example: setting_id: $ref:imported.integrations.git_conn.id`
        );
      }
    }
  }

  /**
   * Resolve a reference path like "imported.integrations.jira_main" or "tool_definitions.jira_tool"
   * Supports nested paths like "imported.integrations.jira_main.id" to access specific fields
   * Returns the referenced object or value from config
   *
   * Special handling for arrays:
   * - imported.integrations (array): searches by 'alias' field
   * - imported.assistants (array): searches by 'name' field
   * - imported.datasources (array): searches by 'name' field
   * - imported.skills (array): searches by 'name' field
   */
  private resolveReference<T>(config: CodemieConfig, ref: string, context: string): T {
    const parts = ref.split('.');

    if (parts.length < 2) {
      throw new Error(
        `Invalid $ref format: "${ref}". ` +
          `Expected format: "imported.integrations.name" or "tool_definitions.name". ` +
          `You can also use nested paths like "imported.integrations.name.id". ` +
          `Referenced in ${context}.`
      );
    }

    let current: unknown = config;
    // Use array for efficient path building instead of string concatenation
    const pathParts: string[] = [];

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      pathParts.push(part);

      if (!current || typeof current !== 'object' || !(part in current)) {
        throw new Error(
          `Reference path "${ref}" not found: "${pathParts.join('.')}" does not exist. ` + `Referenced in ${context}.`
        );
      }

      current = current[part as keyof typeof current];

      // When we encounter an array, the next path segment is used to search for
      // a specific item within that array by a unique identifier field.
      //
      // Examples:
      //   - "imported.integrations.my_jira" → searches for item with alias="my_jira"
      //   - "tool_definitions.create_ticket" → searches for item with name="create_ticket"
      //
      // Search field mapping:
      //   - integrations: use 'alias' field (unique identifier for integrations)
      //   - all others: use 'name' field (standard unique identifier)
      const hasMorePathSegments = i + 1 < parts.length;

      if (Array.isArray(current) && hasMorePathSegments) {
        const nextPathSegment = parts[i + 1];
        const searchField = part === 'integrations' ? 'alias' : 'name';

        const foundItem: unknown = current.find((item) => {
          if (typeof item !== 'object' || item === null) {
            return false;
          }

          const fieldValue = (item as Record<string, unknown>)[searchField];
          if (typeof fieldValue !== 'string') {
            return false;
          }

          return searchField === 'alias' ? fieldValue === nextPathSegment : namesEqual(fieldValue, nextPathSegment);
        });

        if (!foundItem) {
          throw new Error(
            `Reference path "${ref}" not found: no item with ${searchField}="${nextPathSegment}" in "${pathParts.join('.')}". ` +
              `Referenced in ${context}.`
          );
        }

        // Move to the found item and skip the next path segment since we just used it for searching
        current = foundItem;
        pathParts.push(nextPathSegment);
        i++;
      }
    }

    // Allow both objects and primitive values (for nested paths like .id)
    // Objects are needed for toolkits, primitives for datasources with .id suffix
    return current as T;
  }

  /**
   * Apply datasource defaults based on $ref or type
   * Priority: $ref (explicit) > type (fallback)
   */
  private applyDatasourceDefaults(config: CodemieConfig): void {
    if (!config.datasource_defaults || !config.resources.datasources) {
      return;
    }

    config.resources.datasources = config.resources.datasources.map((datasource) => {
      let defaults = null;

      // Priority 1: Explicit $ref (e.g., "$ref: datasource_defaults.standard_code")
      if (datasource.$ref) {
        // Remove "$ref: " prefix if present
        const refPath = datasource.$ref.startsWith('$ref:') ? datasource.$ref.slice(5) : datasource.$ref;

        // Resolve the reference
        defaults = this.resolveReference(config, refPath, `datasource "${datasource.name}".$ref`);

        if (!defaults || typeof defaults !== 'object') {
          throw new Error(
            `Invalid $ref in datasource "${datasource.name}": "${refPath}" ` +
              `does not point to a valid datasource defaults object`
          );
        }
      }
      // Priority 2: Fallback to type-based defaults (only if no $ref)
      else if (datasource.type) {
        defaults = config.datasource_defaults![datasource.type];
      }

      // If no defaults found, return as-is
      if (!defaults) {
        return datasource;
      }

      // Merge: defaults first, then datasource config (datasource overrides defaults)
      // Remove $ref from the final merged object
      const { $ref: _ref, ...datasourceWithoutRef } = datasource;
      return {
        ...defaults,
        ...datasourceWithoutRef,
      };
    });
  }

  /**
   * Type guard to check if value is a plain object (not array, not null)
   */
  private isPlainObject(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  private isRefObject(item: unknown): item is { $ref: string } {
    return this.isPlainObject(item) && '$ref' in item && typeof item.$ref === 'string';
  }

  /**
   * Substitute environment variables in configuration
   * Supports syntax:
   * - $${VAR_NAME} - literal placeholder (not read from the environment)
   * - ${VAR_NAME} - required variable (throws if not set)
   * - ${VAR_NAME:-default} - optional with default value (shell-style)
   * - ${VAR_NAME:default} - optional with default value (simplified)
   * - ${VAR_NAME:-} or ${VAR_NAME:} - optional with empty string default
   */
  private substituteEnvVars<T>(obj: T, configPath: string = ''): void {
    const isArray = Array.isArray(obj);

    for (const key in obj) {
      // `resources.datasources[0].name` rather than a bare variable name, so an unset variable
      // buried in an array element is diagnosable without bisecting the config by hand.
      const childPath = isArray ? `${configPath}[${key}]` : configPath ? `${configPath}.${key}` : key;

      if (typeof obj[key] === 'string') {
        // Match escaped placeholders before ordinary substitutions in a single pass.
        obj[key] = obj[key].replaceAll(
          /\$(\$)?\{([^:}]+)(?::-?([^}]*))?\}/g,
          (match: string, escaped: string | undefined, varName: string, defaultValue: string) => {
            if (escaped) {
              return match.slice(1);
            }
            const value = process.env[varName];
            if (value === undefined) {
              if (defaultValue !== undefined) {
                return defaultValue;
              }
              throw new Error(`Environment variable ${varName} is not set (referenced in ${childPath})`);
            }
            return value;
          }
        ) as T[Extract<keyof T, string>];
      } else if (this.isPlainObject(obj[key]) || Array.isArray(obj[key])) {
        // Recursively process nested objects and array elements (e.g. resources.skills[].source_dir)
        this.substituteEnvVars(obj[key], childPath);
      }
    }
  }
}
