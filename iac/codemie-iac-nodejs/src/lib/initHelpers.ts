/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

import type { AppConfig } from '../appConfig';
import { defaultConfig } from '../appConfig';
import { logger } from './logger';
import { confirmOverwrite, promptUser } from './terminalPromptHelpers';

/**
 * Check if a file exists at the given path
 * @param filePath - Path to check
 * @returns true if file exists, false otherwise
 */
export function fileExists(filePath: string): boolean {
  return fs.existsSync(filePath);
}

/**
 * Generate .env template with all required Codemie variables
 * @returns Content for .env file with placeholders and comments
 */
export function generateEnvTemplate(): string {
  return `# Codemie API Configuration
# Replace these placeholder values with your actual Codemie instance details
# DO NOT commit this file to Git!

# Codemie API endpoint URL
CODEMIE_API_URL=https://your-instance.codemie.ai/api

# Keycloak authentication server URL
CODEMIE_AUTH_URL=https://your-keycloak.auth.com

# Keycloak realm name
CODEMIE_REALM=codemie

# Service account client ID
CODEMIE_CLIENT_ID=your-client-id

# Service account client secret (keep this secure!)
CODEMIE_CLIENT_SECRET=your-client-secret
`;
}

/**
 * Generate minimal codemie.yaml configuration
 * @param projectName - Name of the project
 * @param projectDescription - Description of the project
 * @returns Content for codemie.yaml file
 */
export function generateMinimalCodemieYaml(projectName: string, projectDescription: string): string {
  return `# Codemie Infrastructure as Code Configuration
# For detailed examples and documentation, see:
# - examples/assistant-examples.yaml
# - examples/datasource-examples.yaml
# - examples/workflow-examples.yaml
# - examples/toolkit-examples.yaml
# - examples/modular-config-example/

version: "1"

# Project identification
project:
  name: ${projectName}
  description: ${projectDescription}

# Environment configuration (uses variables from .env file)
environment:
  codemie_api_url: \${CODEMIE_API_URL}
  auth_server_url: \${CODEMIE_AUTH_URL}
  auth_realm_name: \${CODEMIE_REALM}
  client_id: \${CODEMIE_CLIENT_ID}
  client_secret: \${CODEMIE_CLIENT_SECRET}

# Imported resources from existing Codemie platform
# Reference existing assistants, datasources, and integrations to use in your IaC configurations
imported:
  assistants: []
  datasources: []
  integrations: []

# Resources to be managed by IaC
# Add your assistants, datasources, and workflows here
resources:
  assistants: []
  datasources: []
  workflows: []
`;
}

/**
 * Prompt user for app configuration values
 * @returns AppConfig with user-provided values
 */
export async function promptAppConfig(): Promise<AppConfig> {
  const rootDir = await promptUser('Root directory', defaultConfig.rootDir);
  const codemieConfig = await promptUser('Codemie config file path', defaultConfig.codemieConfig);
  const codemieState = await promptUser('Codemie state file path', defaultConfig.codemieState);
  const backupsDirectory = await promptUser('Backups directory', defaultConfig.backupsDirectory);

  return {
    rootDir,
    codemieConfig,
    codemieState,
    backupsDirectory,
  };
}

/**
 * Compare user config with default config to detect differences
 * @param userConfig - Configuration provided by user
 * @returns true if user config differs from defaults, false otherwise
 */
export function compareConfigWithDefaults(userConfig: AppConfig): boolean {
  return (
    userConfig.rootDir !== defaultConfig.rootDir ||
    userConfig.codemieConfig !== defaultConfig.codemieConfig ||
    userConfig.codemieState !== defaultConfig.codemieState ||
    userConfig.backupsDirectory !== defaultConfig.backupsDirectory
  );
}

/**
 * Save app configuration to a JSON file
 * @param config - AppConfig to save
 * @param defaultFilename - Default filename if user doesn't provide one
 * @returns Path to the saved config file
 */
export async function saveConfigFile(config: AppConfig, defaultFilename: string = 'config.json'): Promise<string> {
  const configFilename = await promptUser(`Enter config file path`, defaultFilename);

  const configPath = path.resolve(process.cwd(), configFilename);

  // Check if file exists and confirm overwrite
  if (fileExists(configPath)) {
    const shouldOverwrite = await confirmOverwrite(configFilename);

    if (!shouldOverwrite) {
      throw new Error(`Cancelled: Configuration file not saved.`);
    }
  }

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8');

  return configFilename;
}

/**
 * Display suggestions for running other commands with the generated config
 * @param configFileName - Name of the generated config file
 */
export function suggestConfigUsage(configFileName: string): void {
  logger.info('\n📋 To use this configuration with other commands, add the `-c` flag:\n');
  logger.info(`  codemie-cdk deploy -c ${configFileName}`);
  logger.info(`  codemie-cdk validate -c ${configFileName}`);
  logger.info(`  codemie-cdk preview -c ${configFileName}`);
  logger.info(`  codemie-cdk backup -c ${configFileName}`);
  logger.info(`  codemie-cdk destroy -c ${configFileName}\n`);
}
