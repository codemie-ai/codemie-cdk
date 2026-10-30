/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as crypto from 'node:crypto';

import type {
  AssistantResource,
  IaCMcpServer,
  IaCTool,
  IaCToolkit,
  IntegrationReference,
} from '../types/codemieConfig';

import { logger } from './logger';
import { sanitizeMcpServer } from './mcpSanitizer';

/**
 * Default LLM model used when not specified in assistant configuration.
 */
export const DEFAULT_LLM_MODEL = 'gpt-4';

/**
 * Normalize integration settings to consistent $ref format.
 * Handles both $ref format (from YAML) and resolved format (from ConfigLoader).
 *
 * @param settings - Settings object (either $ref or resolved integration)
 * @returns Normalized settings (always $ref format if it's an integration, otherwise unchanged)
 */
function normalizeIntegrationSettings(settings: IntegrationReference | undefined): IntegrationReference | undefined {
  if (!settings || typeof settings !== 'object') {
    return settings;
  }

  // Already $ref format
  if ('$ref' in settings && typeof settings.$ref === 'string') {
    return { $ref: settings.$ref };
  }

  // Resolved integration format - convert to $ref
  if ('alias' in settings && typeof settings.alias === 'string') {
    return { $ref: `imported.integrations.${settings.alias}` };
  }

  // Plain settings object (not an integration reference)
  return settings;
}

/**
 * Normalize tool for consistent checksum calculation.
 * Explicit key order ensures same checksum regardless of yaml field order.
 */
function normalizeTool(tool: IaCTool): IaCTool {
  return {
    name: tool.name,
    label: tool.label,
    settings_config: tool.settings_config,
    user_description: tool.user_description,
    settings: normalizeIntegrationSettings(tool.settings),
  };
}

/**
 * Normalize toolkits array for consistent checksum calculation.
 * Explicit key order ensures same checksum regardless of yaml field order.
 */
function normalizeToolkits(toolkits: IaCToolkit[] | undefined): IaCToolkit[] {
  if (!toolkits) {
    return [];
  }

  return toolkits.map(({ toolkit, tools, label, settings_config, is_external, settings }) => ({
    toolkit,
    label,
    settings_config,
    is_external,
    tools: tools?.map((tool) => normalizeTool(tool)),
    settings: normalizeIntegrationSettings(settings),
  }));
}

/** True for a non-null, non-array object. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Return a copy with object keys in a stable (alphabetical) order at every object depth.
 * The checksum hashes JSON.stringify output, so without this the incoming key order —
 * the API response order on the backup path, the YAML field order on the import path —
 * would be part of the hash. Arrays pass through by reference: their order and contents
 * are never touched, mirroring the sanitizer.
 */
function sortKeysDeep<T>(value: T): T {
  if (!isPlainObject(value)) {
    return value;
  }

  const sorted: Record<string, unknown> = {};

  for (const key of Object.keys(value).sort()) {
    sorted[key] = sortKeysDeep(value[key]);
  }

  return sorted as T;
}

/**
 * Normalize MCP servers array for consistent checksum calculation.
 * Sorted keys ensure the same checksum regardless of API or yaml field order.
 */
function normalizeMcpServers(mcpServers: IaCMcpServer[] | undefined): IaCMcpServer[] {
  if (!mcpServers) {
    return [];
  }

  return mcpServers.map((mcp) => {
    // Keys carrying no information must not contribute to the hash
    const sanitized = sanitizeMcpServer(mcp);

    // Hand-authored YAML can carry a null or scalar list entry: hash it as-is
    // instead of crashing preview/deploy before the API can report it.
    if (!isPlainObject(sanitized)) {
      return sanitized;
    }

    return sortKeysDeep({
      ...sanitized,
      settings: normalizeIntegrationSettings(sanitized.settings),
      mcp_connect_auth_token: normalizeIntegrationSettings(sanitized.mcp_connect_auth_token),
    });
  });
}

/**
 * Calculate SHA-256 checksum of string content
 * Used for detecting changes in prompts, configs, and YAML files
 *
 * @param content - String content to hash
 * @returns Hexadecimal SHA-256 hash
 * @throws {Error} If content is not a string
 */
export function calculateChecksum(content: string): string {
  if (typeof content !== 'string') {
    throw new TypeError(`calculateChecksum expects string, got ${typeof content}`);
  }

  // Empty string is valid but usually unintended
  if (content.length === 0) {
    logger.warn('⚠️  Calculating checksum of empty string');
  }

  return crypto.createHash('sha256').update(content, 'utf8').digest('hex');
}

/**
 * Normalize assistant configuration for consistent comparison
 * This ensures the same fields are always included in the same order
 * Accepts both SDK Assistant and IaC AssistantResource types
 *
 * Note: `name` is intentionally excluded as it's the identifier, not configuration
 *
 * @param assistant - Assistant from SDK (Assistant) or IaC config (AssistantResource)
 * @param buildConfig - Optional build-time configuration
 * @returns Normalized configuration object
 */
export function normalizeAssistantConfig(assistant: AssistantResource, buildConfig: unknown = null) {
  return {
    description: assistant.description || '',
    model: assistant.model || DEFAULT_LLM_MODEL,
    temperature: assistant.temperature,
    top_p: assistant.top_p,
    shared: assistant.shared,
    is_react: assistant.is_react,
    is_global: assistant.is_global,
    icon_url: assistant.icon_url,
    toolkits: normalizeToolkits(assistant.toolkits),
    context: assistant.context || [],
    mcp_servers: normalizeMcpServers(assistant.mcp_servers),
    assistant_ids: assistant.assistant_ids || [],
    sub_assistants: assistant.sub_assistants || [],
    skills: assistant.skills || [],
    conversation_starters: assistant.conversation_starters || [],
    // Only when non-empty, so legacy checksums stay identical (undefined is dropped by JSON.stringify)
    ...(assistant.deselected_default_tools &&
      assistant.deselected_default_tools.length > 0 && {
        deselected_default_tools: [...new Set(assistant.deselected_default_tools)].sort(),
      }),
    buildConfig,
  };
}

/**
 * Calculate assistant configuration checksum
 * Uses consistent field ordering for both backup and apply operations
 *
 * @param assistant - Assistant from SDK or IaC config
 * @param buildConfig - Optional build-time configuration
 * @returns Configuration checksum
 */
export function calculateAssistantConfigChecksum(assistant: AssistantResource, buildConfig: unknown = null): string {
  const normalized = normalizeAssistantConfig(assistant, buildConfig);
  return calculateChecksum(JSON.stringify(normalized));
}
