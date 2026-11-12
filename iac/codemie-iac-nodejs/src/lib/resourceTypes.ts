/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

/**
 * The resource kinds `codemie-cdk import` knows how to import from the platform.
 */
export type ImportResourceType = 'assistant' | 'datasource' | 'workflow' | 'skill';

export const VALID_RESOURCE_TYPES: ImportResourceType[] = ['assistant', 'datasource', 'workflow', 'skill'];

const PLURAL_BY_RESOURCE_TYPE: Record<ImportResourceType, string> = {
  assistant: 'assistants',
  datasource: 'datasources',
  workflow: 'workflows',
  skill: 'skills',
};

/**
 * The `resources.<plural>` / `state.resources.<plural>` key for a given singular resource type.
 */
export function pluralTypeOf(resourceType: ImportResourceType): string {
  return PLURAL_BY_RESOURCE_TYPE[resourceType];
}
