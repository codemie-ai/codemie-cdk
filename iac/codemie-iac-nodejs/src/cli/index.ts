#!/usr/bin/env node
/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import path from 'node:path';

import { program } from '@commander-js/extra-typings';

import packageJson from '../../package.json' with { type: 'json' };
import { loadAppConfig } from '../appConfig';
import { main as backupMain } from '../backup';
import { main as deployMain } from '../deploy';
import { main as destroyMain } from '../destroy';
import { type ImportResourceType, main as importMain, VALID_RESOURCE_TYPES } from '../import';
import { main as initMain } from '../init';
import { runCommandWithSpinner } from '../lib/commandSpinner';
import { logger } from '../lib/logger';
import { main as previewMain } from '../preview';
import { main as validateMain } from '../validate';

program.name('codemie-cdk').description('Infrastructure as Code for Codemie platform').version(packageJson.version);

program
  .command('init')
  .description('Initialize a new Codemie IaC project')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .action((options) => {
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(undefined, rootDir ?? process.cwd());
    void initMain({ appConfig });
  });

program
  .command('deploy')
  .description('Deploy resources to Codemie platform')
  .option('-p, --prune', 'Delete orphaned resources')
  .option('--skip-datasources', 'Skip the datasource stage entirely (no create/update/delete, no indexing)')
  .option(
    '--replace-skill-group <group>',
    'Delete and recreate every skill labelled with this group (skills get new ids; datasources and workflows are skipped)'
  )
  .option('--yes-replace-skills', 'Confirm the destructive --replace-skill-group run')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .action(async (options) => {
    const configPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(configPath, rootDir);
    await runCommandWithSpinner('Deploying Codemie resources', () =>
      deployMain({
        appConfig,
        prune: options.prune,
        skipDatasources: options.skipDatasources,
        replaceSkillGroup: options.replaceSkillGroup,
        yesReplaceSkills: options.yesReplaceSkills,
      })
    );
  });

program
  .command('backup')
  .description('Backup all resources from Codemie platform')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .action(async (options) => {
    const configPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(configPath, rootDir);
    await runCommandWithSpinner('Backing up Codemie resources', () => backupMain({ appConfig }));
  });

program
  .command('destroy')
  .description('Destroy all IaC-managed resources')
  .option('-f, --force', 'Skip confirmation prompt')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .action(async (options) => {
    const configPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(configPath, rootDir);
    await runCommandWithSpinner('Destroying Codemie resources', () => destroyMain({ appConfig, force: options.force }));
  });

program
  .command('preview')
  .description('Preview changes without applying them')
  .option('--skip-datasources', 'Exclude datasources from preview (mirrors deploy --skip-datasources)')
  .option(
    '--replace-skill-group <group>',
    'Preview the deletes and creates of deploy --replace-skill-group for this skill group'
  )
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .action(async (options) => {
    const appConfigPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(appConfigPath, rootDir);
    await runCommandWithSpinner('Generating Codemie preview', () =>
      previewMain({
        appConfig,
        skipDatasources: options.skipDatasources,
        replaceSkillGroup: options.replaceSkillGroup,
      })
    );
  });

program
  .command('validate')
  .description('Validate configuration')
  .option('-a, --check-api', 'Check for API conflicts')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .action(async (options) => {
    const configPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(configPath, rootDir);
    await runCommandWithSpinner('Validating Codemie configuration', () =>
      validateMain({ appConfig, checkApi: options.checkApi })
    );
  });

program
  .command('import')
  .description('Import a single resource from the CodeMie platform into the local IaC configuration')
  .argument('<type>', 'Resource type: assistant, datasource, workflow, or skill')
  .argument('<slug>', 'Resource slug or name (a platform UUID also works for assistant and workflow)')
  .option('-d, --root-dir <path>', 'Project root directory (containing codemie.yaml)')
  .option('-c, --config <path>', 'Configuration file')
  .option('-u, --update', 'Refresh an already-managed resource in place instead of failing on a conflict')
  .option(
    '--with-skills',
    'Assistants only: also import the project-owned skills it references that are not managed yet'
  )
  .action(async (type, slug, options) => {
    if (!(VALID_RESOURCE_TYPES as readonly string[]).includes(type)) {
      logger.error(`❌ Invalid resource type: "${type}". Must be one of: ${VALID_RESOURCE_TYPES.join(', ')}`);
      process.exitCode = 1;
      return;
    }
    const configPath = options.config ? path.resolve(options.config) : undefined;
    const rootDir = options.rootDir ? path.resolve(options.rootDir) : undefined;
    const appConfig = loadAppConfig(configPath, rootDir);
    await runCommandWithSpinner(`Importing ${type}`, () =>
      importMain({
        appConfig,
        resourceType: type as ImportResourceType,
        slug,
        update: options.update,
        withSkills: options.withSkills,
      })
    );
  });

program.parse();
