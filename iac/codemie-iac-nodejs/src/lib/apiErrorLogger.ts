/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import { logger } from './logger';

function diagnosticJson(value: unknown): string | undefined {
  return JSON.stringify(
    value,
    (key, entry: unknown) =>
      /authorization|cookie|password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token/i.test(key)
        ? '[REDACTED]'
        : entry,
    2
  );
}

/**
 * Log the details of a failed API call in a consistent shape.
 *
 * Handles the SDK ApiError (statusCode + response) before the Axios shape
 * (response.status/data), so SDK errors never report `Status: undefined`.
 */
export function logApiErrorDetails(error: unknown): void {
  if (error instanceof Error) {
    logger.error(`     ${error.message}`);
    logger.debug(`     Stack:`, error.stack);
    // Handle SDK ApiError (uses statusCode + response, not Axios response.status/data)
    if ('statusCode' in error) {
      if (error.statusCode !== undefined) {
        logger.error(`     Status: ${String(error.statusCode)}`);
      }
      logger.error(`     Data: ${diagnosticJson('response' in error ? error.response : undefined)}`);
      if ('request' in error && typeof error.request === 'object' && error.request !== null) {
        const request = error.request as Record<string, unknown>;
        if (typeof request.method === 'string' && typeof request.path === 'string') {
          logger.error(`     Request: ${request.method} ${request.path}`);
        }
        if (typeof request.requestId === 'string') {
          logger.error(`     Request ID: ${request.requestId}`);
        }
        if (typeof request.code === 'string') {
          logger.error(`     Code: ${request.code}`);
        }
      }
    } else if ('response' in error) {
      const axiosError = error as { response: { status: number; data: unknown } };
      logger.error(`     Status: ${axiosError.response?.status}`);
      logger.error(`     Data: ${diagnosticJson(axiosError.response?.data)}`);
    }
  } else {
    logger.error(`     ${String(error)}`);
  }
}
