/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import type { CodeMieClient, AssistantCreateParams } from 'codemie-sdk';

import { logger } from './logger';
import { findAssistantByName } from './paginationUtils';

const ASSISTANT_LOOKUP_RETRY_DELAYS_MS = [250, 500, 1000, 2000, 2000] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** A successful HTTP request can still refuse to save an assistant. */
export class AssistantValidationError extends Error {
  readonly statusCode = 200;

  constructor(
    operation: 'create' | 'update',
    assistantName: string,
    readonly response: unknown
  ) {
    const message = isRecord(response) ? validationMessage(response) : 'Missing integrations';
    super(`Assistant ${operation} validation failed for "${assistantName}": ${message}`);
    this.name = 'AssistantValidationError';
  }
}

function hasMissingIntegrations(response: unknown): response is Record<string, unknown> {
  return isRecord(response) && isRecord(response.validation) && response.validation.has_missing_integrations === true;
}

function validationMessage(response: Record<string, unknown>): string {
  const validation = isRecord(response.validation) ? response.validation : {};
  return typeof validation.message === 'string' ? validation.message : 'Missing integrations';
}

/**
 * An update that reports missing integrations has still been saved; surface the
 * message without failing the deploy, otherwise the same warning would block
 * every future run and the state would never converge.
 */
export function warnOnMissingIntegrations(response: unknown, assistantName: string): void {
  if (hasMissingIntegrations(response)) {
    logger.warn(`  ⚠️  Assistant "${assistantName}" saved with missing integrations: ${validationMessage(response)}`);
  }
}

function extractAssistantId(response: unknown): string | null {
  if (!isRecord(response)) {
    return null;
  }
  for (const key of ['assistant_id', 'assistantId', 'id']) {
    const id = response[key];
    if (typeof id === 'string' && id.trim().length > 0) {
      return id.trim();
    }
  }
  return null;
}

/** Validation and authorization failures cannot be repaired by adopting another ID. */
export function shouldRecoverAssistantCreateError(error: unknown): boolean {
  if (error instanceof AssistantValidationError) {
    return false;
  }
  if (isRecord(error) && typeof error.statusCode === 'number' && error.statusCode >= 400 && error.statusCode < 500) {
    return error.statusCode === 409 || (error instanceof Error && /already exists/i.test(error.message));
  }
  return true;
}

async function findAssistantIdWithRetry(lookup: () => Promise<string | null>): Promise<string | null> {
  for (let attempt = 0; attempt <= ASSISTANT_LOOKUP_RETRY_DELAYS_MS.length; attempt++) {
    try {
      const id = await lookup();
      if (id) {
        return id;
      }
    } catch (error) {
      if (!isRecord(error) || error.statusCode !== 404) {
        throw error;
      }
    }
    const delay = ASSISTANT_LOOKUP_RETRY_DELAYS_MS[attempt];
    if (delay !== undefined) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  return null;
}

/**
 * Creates an assistant and retrieves its UUID
 *
 * Validates the create result and prefers its ID. Older responses without an ID
 * fall back to bounded slug/name lookup while the platform index catches up.
 *
 * @param client - Initialized Codemie client
 * @param params - Assistant creation parameters
 * @param slug - Optional assistant slug for lookup (platform-generated if not provided)
 * @returns Created assistant's UUID
 * @throws Error if assistant cannot be found after creation
 */
export async function createAssistantAndGetId(
  client: CodeMieClient,
  params: AssistantCreateParams,
  slug?: string | null
): Promise<string> {
  const response: unknown = await client.assistants.create(params);
  const returnedId = extractAssistantId(response);

  if (hasMissingIntegrations(response)) {
    // Without an ID the platform refused to save the assistant; with one it was saved with a warning.
    if (!returnedId) {
      throw new AssistantValidationError('create', params.name, response);
    }
    warnOnMissingIntegrations(response, params.name);
  }

  if (returnedId) {
    return returnedId;
  }

  if (slug) {
    const id = await findAssistantIdWithRetry(async () => {
      const created = await client.assistants.getBySlug(slug);
      return created?.id || null;
    });

    if (!id) {
      throw new Error(`Assistant created but not found by slug: ${slug}`);
    }

    return id;
  }

  const assistantId = await findAssistantIdWithRetry(() =>
    findAssistantByName(client, params.name, { isGlobal: params.is_global === true })
  );

  if (!assistantId) {
    throw new Error(`Assistant created but not found by name: ${params.name}`);
  }

  return assistantId;
}
