/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { AppConfig } from './appConfig';
import { initProject, main } from './init';
import * as initHelpers from './lib/initHelpers';
import { logger } from './lib/logger';
import { promptUser, confirmOverwrite } from './lib/terminalPromptHelpers';

jest.mock('./lib/initHelpers');
jest.mock('./lib/logger');
jest.mock('./lib/terminalPromptHelpers', () => ({
  promptUser: jest.fn(),
  confirmOverwrite: jest.fn(),
}));

const mockedInitHelpers = initHelpers as jest.Mocked<typeof initHelpers>;

describe('init', () => {
  let tempDir: string;
  let appConfig: AppConfig;

  beforeEach(() => {
    jest.clearAllMocks();

    // Create temporary directory for each test
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'init-test-'));

    appConfig = {
      rootDir: tempDir,
      codemieConfig: 'codemie.yaml',
      codemieState: 'state.json',
      backupsDirectory: 'backups',
    };

    // Setup default mock implementations
    jest.mocked(promptUser).mockResolvedValue('test-value');
    jest.mocked(confirmOverwrite).mockResolvedValue(true);
    mockedInitHelpers.fileExists.mockReturnValue(false);
    mockedInitHelpers.generateEnvTemplate.mockReturnValue('# Mock .env content');
    mockedInitHelpers.generateMinimalCodemieYaml.mockReturnValue('# Mock codemie.yaml content');
    // New helpers default behavior
    mockedInitHelpers.compareConfigWithDefaults.mockReturnValue(false);
    mockedInitHelpers.saveConfigFile.mockResolvedValue('codemie-app-config.json');
    mockedInitHelpers.suggestConfigUsage.mockImplementation(() => {});
  });

  afterEach(() => {
    // Clean up temporary directory
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  describe('initProject', () => {
    it('should successfully create both .env and codemie.yaml files when they do not exist', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await initProject({ appConfig });

      // Verify files were created
      const envPath = path.join(tempDir, '.env');
      const configPath = path.join(tempDir, 'codemie.yaml');

      expect(fs.existsSync(envPath)).toBe(true);
      expect(fs.existsSync(configPath)).toBe(true);

      // Verify content
      expect(fs.readFileSync(envPath, 'utf-8')).toBe('# Mock .env content');
      expect(fs.readFileSync(configPath, 'utf-8')).toBe('# Mock codemie.yaml content');

      // Verify logger calls
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('🚀 Initialize Codemie IaC Project'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('✓ Created .env'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('✓ Created codemie.yaml'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('🎉 Initialization complete!'));
    });

    it('should prompt user for project name and description', async () => {
      await initProject({ appConfig });

      expect(promptUser).toHaveBeenCalledWith('Project name', 'my-codemie-project');
      expect(promptUser).toHaveBeenCalledWith(
        'Project description',
        'AI assistants and workflows managed with Codemie IaC'
      );
    });

    it('should use prompted values when generating config', async () => {
      const projectName = 'test-project';
      const projectDesc = 'Test description';

      jest.mocked(promptUser).mockResolvedValueOnce(projectName).mockResolvedValueOnce(projectDesc);

      await initProject({ appConfig });

      expect(mockedInitHelpers.generateMinimalCodemieYaml).toHaveBeenCalledWith(projectName, projectDesc);
    });

    it('should handle existing .env file and prompt for overwrite', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      mockedInitHelpers.fileExists.mockImplementation((filePath: string) => {
        return filePath.endsWith('.env');
      });

      jest.mocked(confirmOverwrite).mockResolvedValue(true);

      await initProject({ appConfig });

      expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining("⚠️  File '.env' already exists"));
      expect(confirmOverwrite).toHaveBeenCalledWith('.env');

      // Should still create the file
      expect(fs.existsSync(path.join(tempDir, '.env'))).toBe(true);
    });

    it('should skip creating .env file if user declines overwrite', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      mockedInitHelpers.fileExists.mockImplementation((filePath: string) => {
        return filePath.endsWith('.env');
      });

      jest.mocked(confirmOverwrite).mockResolvedValue(false);

      await initProject({ appConfig });

      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('Keeping existing .env file'));

      // .env should not be created
      expect(fs.existsSync(path.join(tempDir, '.env'))).toBe(false);

      // codemie.yaml should still be created
      expect(fs.existsSync(path.join(tempDir, 'codemie.yaml'))).toBe(true);
    });

    it('should exit early if both files exist and user declines both overwrites', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      mockedInitHelpers.fileExists.mockReturnValue(true);
      jest.mocked(confirmOverwrite).mockResolvedValue(false);

      await initProject({ appConfig });

      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('✓ No files created (all existing files kept)'));

      // Neither file should be created
      expect(fs.existsSync(path.join(tempDir, '.env'))).toBe(false);
      expect(fs.existsSync(path.join(tempDir, 'codemie.yaml'))).toBe(false);

      // Should not show completion message
      expect(logger.info).not.toHaveBeenCalledWith(expect.stringContaining('🎉 Initialization complete!'));
    });

    it('should show warnings about .env security when creating it', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await initProject({ appConfig });

      expect(logger.warn).toHaveBeenCalledWith(
        expect.stringContaining('⚠️  Remember to fill in your actual credentials!')
      );
      expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('⚠️  DO NOT commit .env to Git!'));
    });

    it('should display next steps after successful initialization', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await initProject({ appConfig });

      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('Next steps:'));
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining('Edit .env and add your Codemie API credentials')
      );
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('Run "codemie-cdk validate"'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('Run "codemie-cdk deploy"'));
    });

    it('should reference example files in the output', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await initProject({ appConfig });

      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('examples/assistant-examples.yaml'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('examples/datasource-examples.yaml'));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('examples/workflow-examples.yaml'));
    });

    it('should use custom config file name from appConfig', async () => {
      const customAppConfig: AppConfig = {
        ...appConfig,
        codemieConfig: 'custom-config.yaml',
      };

      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await initProject({ appConfig: customAppConfig });

      const configPath = path.join(tempDir, 'custom-config.yaml');
      expect(fs.existsSync(configPath)).toBe(true);
    });

    it('should handle errors during file creation', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      mockedInitHelpers.generateEnvTemplate.mockImplementation(() => {
        throw new Error('Failed to generate template');
      });

      const mockExit = jest.spyOn(process, 'exit').mockImplementation((code?: string | number | null | undefined) => {
        throw new Error(`process.exit: ${code}`);
      });

      await expect(initProject({ appConfig })).rejects.toThrow('process.exit: 1');

      expect(logger.error).toHaveBeenCalledWith(
        expect.stringContaining('❌ Initialization failed: Failed to generate template')
      );

      mockExit.mockRestore();
    });

    it('should handle errors during user prompts', async () => {
      jest.mocked(promptUser).mockRejectedValue(new Error('User input failed'));

      const mockExit = jest.spyOn(process, 'exit').mockImplementation((code?: string | number | null | undefined) => {
        throw new Error(`process.exit: ${code}`);
      });

      await expect(initProject({ appConfig })).rejects.toThrow('process.exit: 1');

      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('❌ Initialization failed: User input failed'));

      mockExit.mockRestore();
    });

    // Newly added functionality tests
    it('should save non-default app configuration and suggest config usage', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('proj').mockResolvedValueOnce('desc');

      mockedInitHelpers.compareConfigWithDefaults.mockReturnValue(true);
      mockedInitHelpers.saveConfigFile.mockResolvedValue('codemie-app-config.json');

      await initProject({ appConfig });

      expect(mockedInitHelpers.saveConfigFile).toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining('✓ Configuration saved to codemie-app-config.json')
      );
      expect(mockedInitHelpers.suggestConfigUsage).toHaveBeenCalledWith('codemie-app-config.json');
    });

    it('should continue when saving app config fails and log a warning', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('proj').mockResolvedValueOnce('desc');

      mockedInitHelpers.compareConfigWithDefaults.mockReturnValue(true);
      mockedInitHelpers.saveConfigFile.mockRejectedValue(new Error('write failed'));

      await initProject({ appConfig });

      expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('⚠️  write failed'));
      expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('Continuing with project initialization...'));
      // Files should still be created despite config save failure
      expect(fs.existsSync(path.join(tempDir, '.env'))).toBe(true);
      expect(fs.existsSync(path.join(tempDir, 'codemie.yaml'))).toBe(true);
    });

    it('should handle existing codemie.yaml and skip when user declines overwrite', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('proj').mockResolvedValueOnce('desc');

      mockedInitHelpers.fileExists.mockImplementation((filePath: string) => {
        return filePath.endsWith('codemie.yaml');
      });

      jest.mocked(confirmOverwrite).mockResolvedValue(false);

      await initProject({ appConfig });

      expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining(`⚠️  File 'codemie.yaml' already exists`));
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('Keeping existing codemie.yaml file'));
      // Should still create .env
      expect(fs.existsSync(path.join(tempDir, '.env'))).toBe(true);
      // Should not create codemie.yaml
      expect(fs.existsSync(path.join(tempDir, 'codemie.yaml'))).toBe(false);
    });
  });

  describe('main', () => {
    it('should call initProject with provided options', async () => {
      jest.mocked(promptUser).mockResolvedValueOnce('my-project').mockResolvedValueOnce('My project description');

      await main({ appConfig });

      expect(promptUser).toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('🎉 Initialization complete!'));
    });

    it('should propagate errors from initProject', async () => {
      jest.mocked(promptUser).mockRejectedValue(new Error('Test error'));

      const mockExit = jest.spyOn(process, 'exit').mockImplementation((code?: string | number | null | undefined) => {
        throw new Error(`process.exit: ${code}`);
      });

      await expect(main({ appConfig })).rejects.toThrow();

      mockExit.mockRestore();
    });
  });
});
