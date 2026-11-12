/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

import type { AppConfig } from './appConfig';
import {
  compareConfigWithDefaults,
  fileExists,
  generateEnvTemplate,
  generateMinimalCodemieYaml,
  promptAppConfig,
  saveConfigFile,
  suggestConfigUsage,
} from './lib/initHelpers';
import { logger } from './lib/logger';
import { confirmOverwrite, promptUser } from './lib/terminalPromptHelpers';

export interface InitOptions {
  appConfig: AppConfig;
}

/**
 * Initialize a new Codemie IaC project
 * Creates .env and codemie.yaml configuration files interactively
 */
export async function initProject(options: InitOptions): Promise<void> {
  logger.info('🚀 Initialize Codemie IaC Project\n\n');

  try {
    const { appConfig } = options;

    // Resolve absolute paths for config files
    const envPath = path.resolve(appConfig.rootDir, '.env');
    const configPath = path.resolve(appConfig.rootDir, appConfig.codemieConfig);

    logger.info('This wizard will create the following files:');
    logger.info(`  📄 .env - Environment variables with API credentials`);
    logger.info(`  📄 ${appConfig.codemieConfig} - Codemie IaC configuration\n\n`);

    // Prompt for project details
    logger.info('📝 Project Information\n');
    const projectName = await promptUser('Project name', 'my-codemie-project');

    const projectDescription = await promptUser(
      'Project description',
      'AI assistants and workflows managed with Codemie IaC'
    );

    // Prompt for app configuration
    logger.info('\n📋 Application Configuration\n');
    logger.info('Configure where Codemie IaC will store files and state:\n');
    const userAppConfig = await promptAppConfig();

    // Check if config differs from defaults
    let configFileName: string | undefined;
    if (compareConfigWithDefaults(userAppConfig)) {
      try {
        configFileName = await saveConfigFile(userAppConfig);
        logger.info(`✓ Configuration saved to ${configFileName}\n`);
      } catch (error) {
        logger.warn(`\n⚠️  ${error instanceof Error ? error.message : String(error)}`);
        logger.warn('Continuing with project initialization...\n');
      }
    } else {
      logger.info('✓ Using default configuration\n');
    }

    // Check and handle .env file
    let shouldCreateEnv = true;

    if (fileExists(envPath)) {
      logger.warn(`⚠️  File '.env' already exists`);
      shouldCreateEnv = await confirmOverwrite('.env');
      if (!shouldCreateEnv) {
        logger.info('   Keeping existing .env file\n');
      }
    }

    // Check and handle codemie.yaml file
    let shouldCreateConfig = true;
    if (fileExists(configPath)) {
      logger.warn(`⚠️  File '${appConfig.codemieConfig}' already exists`);
      shouldCreateConfig = await confirmOverwrite(appConfig.codemieConfig);
      if (!shouldCreateConfig) {
        logger.info(`   Keeping existing ${appConfig.codemieConfig} file\n`);
      }
    }

    // Check if both files were skipped
    if (!shouldCreateEnv && !shouldCreateConfig) {
      logger.info('✓ No files created (all existing files kept)\n');
      return;
    }

    logger.info('\n📁 Creating configuration files...\n');

    // Create .env file
    if (shouldCreateEnv) {
      const envContent = generateEnvTemplate();
      fs.writeFileSync(envPath, envContent, 'utf-8');
      logger.info(`✓ Created .env`);
      logger.warn(`  ⚠️  Remember to fill in your actual credentials!`);
      logger.warn(`  ⚠️  DO NOT commit .env to Git!\n`);
    }

    // Create codemie.yaml file
    if (shouldCreateConfig) {
      const configContent = generateMinimalCodemieYaml(projectName, projectDescription);
      fs.writeFileSync(configPath, configContent, 'utf-8');
      logger.info(`✓ Created ${appConfig.codemieConfig}`);
      logger.info(`  See examples/ directory for detailed configuration examples\n\n`);
    }

    logger.info('🎉 Initialization complete!\n');
    logger.info('Next steps:');
    logger.info('  1. Edit .env and add your Codemie API credentials');
    logger.info(`  2. Edit ${appConfig.codemieConfig} and add your resources`);
    logger.info('  3. Run "codemie-cdk validate" to check your configuration');
    logger.info('  4. Run "codemie-cdk deploy" to deploy your resources\n');

    if (configFileName) {
      suggestConfigUsage(configFileName);
    }

    logger.info('📚 For examples and documentation, see:');
    logger.info('  • examples/assistant-examples.yaml');
    logger.info('  • examples/datasource-examples.yaml');
    logger.info('  • examples/workflow-examples.yaml');
    logger.info('  • examples/modular-config-example/\n');
  } catch (error) {
    logger.error(`\n❌ Initialization failed: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  }
}

/**
 * Main entry point for init command
 */
export async function main(options: InitOptions): Promise<void> {
  await initProject(options);
}
