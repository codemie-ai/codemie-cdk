/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { Assistant, CodeMieClient, DataSource, SkillDetail, Workflow } from 'codemie-sdk';
import * as yaml from 'yaml';

import { type ImportOptions, importResource, main } from './import';
import { createClient } from './lib/clientFactory';
import { CodemieConfigLoader } from './lib/codemieConfigLoader';
import { logger } from './lib/logger';
import { StateManager } from './lib/stateManager';
import { createMockAssistant, createMockSkill } from './testFixtures';
import type { CodemieConfig, SkillResource } from './types/codemieConfig';

// Mock external dependencies
jest.mock('./lib/clientFactory');
jest.mock('./lib/codemieConfigLoader');

const mockCreateClient = createClient as jest.MockedFunction<typeof createClient>;
const MockedConfigLoader = CodemieConfigLoader as jest.MockedClass<typeof CodemieConfigLoader>;

function createMockConfig(): CodemieConfig {
  return {
    version: '1',
    project: { name: 'test-project', description: 'Test' },
    environment: {
      codemie_api_url: 'https://api.example.com',
      auth_server_url: 'https://auth.example.com',
      auth_realm_name: 'test',
      client_id: 'test-client',
      client_secret: 'secret',
    },
    imported: {
      assistants: [],
      datasources: [],
      skills: [],
      integrations: [
        {
          id: 'int-123',
          alias: 'my-git',
          credential_type: 'Git',
          project_name: 'test-project',
          setting_type: 'project',
        } as CodemieConfig['imported']['integrations'][0],
      ],
    },
    resources: {
      assistants: [],
      datasources: [],
      workflows: [],
      skills: [],
    },
  };
}

function createMockDatasource(overrides: Partial<DataSource> = {}): DataSource {
  return {
    id: 'ds-123',
    name: 'test-repo',
    description: 'A test datasource',
    type: 'code',
    project_name: 'test-project',
    status: 'completed',
    shared_with_project: true,
    setting_id: 'int-123',
    embeddings_model: 'titan',
    created_date: '2025-01-01',
    created_by: { id: 'user-1', name: 'Test User', image_url: '' },
    update_date: '2025-01-01',
    user_abilities: [],
    code: {
      link: 'https://github.com/example/repo',
      branch: 'main',
      indexType: 'code',
    },
    ...overrides,
  } as DataSource;
}

function createMockWorkflow(overrides: Partial<Workflow> = {}): Workflow {
  return {
    id: 'wf-123',
    name: 'Test Workflow',
    description: 'A test workflow',
    project: 'test-project',
    mode: 'Sequential',
    shared: true,
    yaml_config: 'assistants:\n  - name: test\n',
    date: '2025-01-01',
    update_date: '2025-01-01',
    created_by: { id: 'user-1', name: 'Test User', image_url: '' },
    ...overrides,
  } as Workflow;
}

describe('import.ts', () => {
  let tempDir: string;
  let mockAppConfig: ImportOptions['appConfig'];
  let mockConfig: CodemieConfig;

  beforeEach(() => {
    jest.clearAllMocks();
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'import-test-'));

    mockAppConfig = {
      rootDir: tempDir,
      codemieConfig: 'codemie.yaml',
      codemieState: '.codemie/state.json',
      backupsDirectory: 'backups',
    };

    mockConfig = createMockConfig();

    // Write a minimal codemie.yaml
    const yamlContent = yaml.stringify({
      version: '1',
      project: mockConfig.project,
      environment: mockConfig.environment,
      imported: { assistants: [], datasources: [], skills: [], integrations: [] },
      resources: {
        assistants: [],
        datasources: [],
        workflows: [],
        skills: [],
      },
    });
    fs.writeFileSync(path.join(tempDir, 'codemie.yaml'), yamlContent, 'utf8');

    // Setup config loader mock
    MockedConfigLoader.mockImplementation(
      () =>
        ({
          loadConfig: jest.fn().mockReturnValue(mockConfig),
          loadPrompt: jest.fn(),
          loadAssistantConfig: jest.fn(),
          loadSkillContent: jest.fn(),
        }) as unknown as CodemieConfigLoader
    );

    // Suppress console output during tests
    jest.spyOn(console, 'log').mockImplementation();
    jest.spyOn(console, 'error').mockImplementation();
  });

  afterEach(() => {
    process.exitCode = undefined;
    fs.rmSync(tempDir, { recursive: true, force: true });
    jest.restoreAllMocks();
  });

  describe('Invalid input handling', () => {
    it('should reject invalid resource type', async () => {
      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'invalid' as ImportOptions['resourceType'],
          slug: 'test',
        })
      ).rejects.toThrow('Invalid resource type: "invalid"');
    });

    it('should reject if resource already exists in config', async () => {
      mockConfig.resources.datasources = [{ name: 'test-repo', type: 'code', description: 'exists' } as any];

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'datasource',
          slug: 'test-repo',
        })
      ).rejects.toThrow('already exists in the configuration');
    });
  });

  describe('Assistant import', () => {
    it('should import assistant by slug', async () => {
      const mockAssistant = createMockAssistant();

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      // Verify prompt file was created
      expect(fs.existsSync(path.join(tempDir, 'system_prompts', 'test-assistant.prompt.md'))).toBe(true);
      const promptContent = fs.readFileSync(path.join(tempDir, 'system_prompts', 'test-assistant.prompt.md'), 'utf8');
      expect(promptContent).toBe('# Test Prompt\nYou are a test assistant.');

      // Verify resource YAML was created
      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      expect(fs.existsSync(resourcePath)).toBe(true);

      // Verify codemie.yaml was updated
      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('configs/imported-resources/assistants/test-assistant.yaml');

      // Verify state was updated
      const statePath = path.join(tempDir, '.codemie', 'state.json');
      expect(fs.existsSync(statePath)).toBe(true);
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      expect(state.resources.assistants['Test Assistant']).toBeDefined();
      expect(state.resources.assistants['Test Assistant'].id).toBe('ast-123');
    });

    it('should fall back to name search if slug lookup fails', async () => {
      const mockAssistant = createMockAssistant({ slug: undefined });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockRejectedValue(new Error('Not found')),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([{ id: 'ast-123', name: 'Test Assistant' }]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'Test Assistant',
      });

      expect(mockClient.assistants.getBySlug).toHaveBeenCalledWith('Test Assistant');
      expect(mockClient.assistants.list).toHaveBeenCalled();
      expect(mockClient.assistants.get).toHaveBeenCalledWith('ast-123');
    });

    it('should resolve skill_ids to skill names on import', async () => {
      const mockSkill = createMockSkill({ id: 'sk-abc', name: 'My Skill' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-abc'] });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockSkill) },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      expect(mockClient.skills.get).toHaveBeenCalledWith('sk-abc');

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      const resourceContent = fs.readFileSync(resourcePath, 'utf8');
      expect(resourceContent).toContain('My Skill');

      const statePath = path.join(tempDir, '.codemie', 'state.json');
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      expect(state.resources.assistants['Test Assistant'].configChecksum).toBeDefined();
    });

    it('should add external assistant skills to imported.skills on assistant import', async () => {
      const mockSkill = createMockSkill({ id: 'sk-external', name: 'External Skill', project: 'other-project' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-external'] });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockSkill) },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      const updatedYaml = yaml.parse(fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8')) as CodemieConfig;
      expect(updatedYaml.imported.skills).toEqual([{ name: 'External Skill', id: 'sk-external' }]);

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      const resourceContent = fs.readFileSync(resourcePath, 'utf8');
      expect(resourceContent).toContain('External Skill');
    });

    it('refreshes a renamed external skill in imported.skills under --update instead of appending a second entry', async () => {
      mockConfig.imported.skills = [{ name: 'Old Skill Name', id: 'sk-external' }];
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        yaml.stringify({
          version: '1',
          project: mockConfig.project,
          environment: mockConfig.environment,
          imported: {
            assistants: [],
            datasources: [],
            skills: [{ name: 'Old Skill Name', id: 'sk-external' }],
            integrations: [],
          },
          resources: { assistants: [], datasources: [], workflows: [], skills: [] },
        }),
        'utf8'
      );

      const mockSkill = createMockSkill({ id: 'sk-external', name: 'New Skill Name', project: 'other-project' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-external'] });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockSkill) },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        update: true,
      });

      const updatedYaml = yaml.parse(fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8')) as CodemieConfig;
      expect(updatedYaml.imported.skills).toEqual([{ name: 'New Skill Name', id: 'sk-external' }]);
    });

    it('should reject an external skill already in imported.skills under a different id, without --update', async () => {
      mockConfig.imported.skills = [{ name: 'External Skill', id: 'sk-old' }];
      const yamlContent = yaml.stringify({
        version: '1',
        project: mockConfig.project,
        environment: mockConfig.environment,
        imported: { assistants: [], datasources: [], skills: mockConfig.imported.skills, integrations: [] },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [],
          skills: [],
        },
      });
      fs.writeFileSync(path.join(tempDir, 'codemie.yaml'), yamlContent, 'utf8');

      const mockSkill = createMockSkill({ id: 'sk-external', name: 'External Skill', project: 'other-project' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-external'] });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockSkill) },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: 'test-assistant',
        })
      ).rejects.toThrow('already exists in imported.skills with a different ID');
    });

    it('should reject assistant import when external skill conflicts with resources.skills', async () => {
      mockConfig.resources.skills = [
        { name: 'External Skill', description: 'Managed duplicate', file: 'skills/external-skill.skill.md' },
      ];
      const mockSkill = createMockSkill({ id: 'sk-external', name: 'External Skill', project: 'other-project' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-external'] });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockSkill) },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: 'test-assistant',
        })
      ).rejects.toThrow('already defined in resources.skills');
    });

    it('should write MCP servers free of null keys when the integration alias map is empty', async () => {
      // Empty alias map: the assistant reaches YAML through convertMcpServers only
      mockConfig.imported.integrations = [];

      const mockAssistant = createMockAssistant({
        mcp_servers: [
          {
            name: 'Figma',
            description: 'Figma MCP',
            enabled: true,
            command: 'npx',
            arguments: '-y figma-developer-mcp --stdio',
            config: null,
            mcp_connect_url: '',
            tools_tokens_size_limit: null,
            mcp_connect_auth_token: null,
          },
        ] as unknown as ReturnType<typeof createMockAssistant>['mcp_servers'],
      });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      const resourceContent = yaml.parse(fs.readFileSync(resourcePath, 'utf8'));

      expect(resourceContent.mcp_servers).toHaveLength(1);
      const mcp = resourceContent.mcp_servers[0];
      expect(mcp).not.toHaveProperty('config');
      expect(mcp).not.toHaveProperty('mcp_connect_url');
      expect(mcp).not.toHaveProperty('tools_tokens_size_limit');
      expect(mcp).not.toHaveProperty('mcp_connect_auth_token');
      expect(mcp).toMatchObject({ name: 'Figma', command: 'npx' });
    });

    it('should import assistant by UUID without calling getBySlug or list', async () => {
      const uuid = '11111111-1111-1111-1111-111111111111';
      const mockAssistant = createMockAssistant({ id: uuid });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
      });

      expect(mockClient.assistants.get).toHaveBeenCalledTimes(1);
      expect(mockClient.assistants.get).toHaveBeenCalledWith(uuid);
      expect(mockClient.assistants.getBySlug).not.toHaveBeenCalled();
      expect(mockClient.assistants.list).not.toHaveBeenCalled();
    });

    it('omits the prompt key on a new import when the platform returns no system_prompt', async () => {
      const mockAssistant = createMockAssistant({ system_prompt: '' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      expect(fs.existsSync(path.join(tempDir, 'system_prompts', 'test-assistant.prompt.md'))).toBe(false);

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      const resourceContent = yaml.parse(fs.readFileSync(resourcePath, 'utf8'));
      expect(resourceContent.prompt).toBeUndefined();
    });

    it('should reject an assistant UUID import when the resolved name already exists in config', async () => {
      const uuid = '22222222-2222-2222-2222-222222222222';
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
        })
      ).rejects.toThrow(/already exists in the configuration/);
    });

    it('should preserve config-id-only MCP servers when integration alias map is populated', async () => {
      const mockAssistant = createMockAssistant({
        mcp_servers: [
          {
            name: 'RI-logs',
            description: 'Download, unzip and grep log files',
            enabled: true,
            mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
            resolve_dynamic_values_in_arguments: false,
            tools: ['fetch_logs'],
            config: null,
            mcp_connect_url: '',
            tools_tokens_size_limit: null,
          },
        ] as unknown as ReturnType<typeof createMockAssistant>['mcp_servers'],
      });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
      });

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      const resourceContent = yaml.parse(fs.readFileSync(resourcePath, 'utf8'));

      expect(resourceContent.mcp_servers).toHaveLength(1);
      expect(resourceContent.mcp_servers[0]).toMatchObject({
        name: 'RI-logs',
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        resolve_dynamic_values_in_arguments: false,
        tools: ['fetch_logs'],
      });
      expect(resourceContent.mcp_servers[0]).not.toHaveProperty('config');
      expect(resourceContent.mcp_servers[0]).not.toHaveProperty('mcp_connect_url');
      expect(resourceContent.mcp_servers[0]).not.toHaveProperty('tools_tokens_size_limit');
    });
  });

  describe('--with-skills', () => {
    function createSkillAwareClient(mockAssistant: Assistant, mockSkill: SkillDetail): CodeMieClient {
      return {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest.fn().mockResolvedValue([]),
          getCompanionFile: jest.fn(),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;
    }

    it('imports a referenced project-owned skill missing from the config into resources.skills', async () => {
      const mockSkill = createMockSkill({ id: 'sk-abc', name: 'My Skill' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-abc'] });
      mockCreateClient.mockResolvedValue(createSkillAwareClient(mockAssistant, mockSkill));

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        withSkills: true,
      });

      expect(fs.existsSync(path.join(tempDir, 'skills', 'my-skill.skill.md'))).toBe(true);
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'skills', 'my-skill.yaml'))).toBe(true);

      const rawYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(rawYaml).toContain('configs/imported-resources/skills/my-skill.yaml');

      const updatedYaml = yaml.parse(rawYaml) as CodemieConfig;
      expect(updatedYaml.imported.skills).toEqual([]);

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8')) as {
        resources: { skills: Record<string, { id: string }> };
      };
      expect(state.resources.skills['My Skill']?.id).toBe('sk-abc');

      // The assistant keeps referencing its skills by name — no skill_ids key is ever written.
      const assistantYaml = yaml.parse(
        fs.readFileSync(
          path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml'),
          'utf8'
        )
      ) as Record<string, unknown>;
      expect(assistantYaml.skills).toEqual(['My Skill']);
      expect(assistantYaml).not.toHaveProperty('skill_ids');
    });

    it('still records a skill owned by another project in imported.skills under --with-skills', async () => {
      const mockSkill = createMockSkill({ id: 'sk-external', name: 'External Skill', project: 'other-project' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-external'] });
      mockCreateClient.mockResolvedValue(createSkillAwareClient(mockAssistant, mockSkill));

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        withSkills: true,
      });

      const rawYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      const updatedYaml = yaml.parse(rawYaml) as CodemieConfig;
      expect(updatedYaml.imported.skills).toEqual([{ name: 'External Skill', id: 'sk-external' }]);

      expect(fs.existsSync(path.join(tempDir, 'skills', 'external-skill.skill.md'))).toBe(false);
      expect(rawYaml).not.toContain('configs/imported-resources/skills/external-skill.yaml');
    });

    it('leaves a referenced skill already managed in resources.skills alone', async () => {
      mockConfig.resources.skills = [
        { name: 'My Skill', description: 'already managed', file: 'skills/my-skill.skill.md' },
      ];
      const mockSkill = createMockSkill({ id: 'sk-abc', name: 'My Skill' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-abc'] });
      const mockClient = createSkillAwareClient(mockAssistant, mockSkill);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        withSkills: true,
      });

      expect(mockClient.skills.listCompanionFiles).not.toHaveBeenCalled();
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'skills', 'my-skill.yaml'))).toBe(false);

      const rawYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(rawYaml).not.toContain('configs/imported-resources/skills/my-skill.yaml');
      expect((yaml.parse(rawYaml) as CodemieConfig).imported.skills).toEqual([]);
    });

    it('skips a referenced skill whose platform id state.json already manages under another name', async () => {
      const warnSpy = jest.spyOn(logger, 'warn').mockImplementation();
      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateSkillState('Old Skill Name', 'sk-abc', 'x', { name: 'Old Skill Name' } as SkillResource);

      const mockSkill = createMockSkill({ id: 'sk-abc', name: 'My Skill' });
      const mockAssistant = createMockAssistant({ skill_ids: ['sk-abc'] });
      const mockClient = createSkillAwareClient(mockAssistant, mockSkill);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        withSkills: true,
      });

      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('already managed under the name "Old Skill Name"'));
      expect(mockClient.skills.listCompanionFiles).not.toHaveBeenCalled();
      expect(fs.existsSync(path.join(tempDir, 'skills', 'my-skill.skill.md'))).toBe(false);
    });

    it('warns and ignores --with-skills on a non-assistant resource type', async () => {
      const warnSpy = jest.spyOn(logger, 'warn').mockImplementation();
      const mockWorkflow = createMockWorkflow();

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: {
          list: jest.fn().mockResolvedValue([{ id: 'wf-123', name: 'Test Workflow' }]),
          get: jest.fn().mockResolvedValue(mockWorkflow),
        },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'workflow',
        slug: 'Test Workflow',
        withSkills: true,
      });

      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('--with-skills only applies to assistants'));
      expect(fs.existsSync(path.join(tempDir, 'configs', 'workflows', 'test-workflow.yaml'))).toBe(true);
    });
  });

  describe('--update flag and conflict detection', () => {
    it('rejects a resolved-name clash without --update, telling the user to re-run with --update or remove it', async () => {
      const uuid = '66666666-6666-6666-6666-666666666666';
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
        })
      ).rejects.toThrow(
        'A assistant named "Test Assistant" already exists in the configuration. ' +
          'Re-run with --update to replace it with the platform version, or remove it first.'
      );
    });

    it('rejects a clash on the typed name without --update, with the same --update hint', async () => {
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: 'Test Assistant',
        })
      ).rejects.toThrow(
        'A assistant named "Test Assistant" already exists in the configuration. ' +
          'Re-run with --update to replace it with the platform version, or remove it first.'
      );
    });

    it('rejects an import when the platform id is already managed under a different name, without --update', async () => {
      const uuid = '77777777-7777-7777-7777-777777777777';
      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Old Name', uuid, 'x', {} as any);

      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
        })
      ).rejects.toThrow(
        `This assistant (id ${uuid}) is already managed by this project under the name "Old Name", ` +
          `but is now named "Test Assistant" on the platform.`
      );
    });

    it('refuses to guess when two state entries share one platform id', async () => {
      const uuid = '99999999-9999-9999-9999-999999999990';
      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('First Name', uuid, 'x', {} as any);
      stateManager.updateAssistantState('Second Name', uuid, 'x', {} as any);

      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
          update: true,
        })
      ).rejects.toThrow(
        `state.json is ambiguous: 2 assistants entries share platform id ${uuid} ("First Name", "Second Name"). ` +
          'Remove the duplicate entries so this assistant can be matched unambiguously.'
      );
    });

    it('throws neither conflict error when update is true', async () => {
      const uuid = '88888888-8888-8888-8888-888888888888';
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Old Name', uuid, 'x', {} as any);

      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const mockClient = {
        assistants: {
          getBySlug: jest.fn(),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
          update: true,
        })
      ).resolves.toBeUndefined();
    });
  });

  describe('--update in-place rewrite', () => {
    function writeCodemieYaml(resourcesAssistants: unknown[]): void {
      const yamlContent = yaml.stringify({
        version: '1',
        project: mockConfig.project,
        environment: mockConfig.environment,
        imported: { assistants: [], datasources: [], skills: [], integrations: [] },
        resources: {
          assistants: resourcesAssistants,
          datasources: [],
          workflows: [],
          skills: [],
        },
      });
      fs.writeFileSync(path.join(tempDir, 'codemie.yaml'), yamlContent, 'utf8');
    }

    function buildAssistantClient(mockAssistant: ReturnType<typeof createMockAssistant>): CodeMieClient {
      return {
        assistants: {
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          get: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn().mockResolvedValue([]),
        },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;
    }

    it('rewrites a single-resource file in place without adding a second $import to codemie.yaml', async () => {
      const uuid = '99999999-9999-9999-9999-999999999999';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      fs.writeFileSync(
        path.join(resourceDir, 'test-assistant.yaml'),
        'name: Test Assistant\ndescription: Old desc\nprompt: system_prompts/test-assistant.prompt.md\nmodel: old-model\n',
        'utf8'
      );
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/test-assistant.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      const occurrences = updatedYaml.split('configs/imported-resources/assistants/test-assistant.yaml').length - 1;
      expect(occurrences).toBe(1);

      const resourceContent = fs.readFileSync(path.join(resourceDir, 'test-assistant.yaml'), 'utf8');
      expect(resourceContent).toContain('description: A test assistant');
    });

    it('leaves the untouched sibling byte-identical in a two-item list file while refreshing the target', async () => {
      const uuid = '99999999-9999-9999-9999-999999999998';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      const listFilePath = path.join(resourceDir, 'team.yaml');
      const listContent =
        '- name: Test Assistant\n' +
        '  description: Old assistant\n' +
        '  prompt: system_prompts/test-assistant.prompt.md\n' +
        '  model: old-model\n' +
        '# keep this one untouched\n' +
        '- name: Sibling Assistant\n' +
        '  description: Sibling untouched\n' +
        '  prompt: system_prompts/sibling.prompt.md\n' +
        '  model: sibling-model\n';
      fs.writeFileSync(listFilePath, listContent, 'utf8');
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/team.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any, { name: 'Sibling Assistant' } as any];

      const marker = '# keep this one untouched';
      const beforeSuffix = listContent.slice(listContent.indexOf(marker));

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      const after = fs.readFileSync(listFilePath, 'utf8');
      const afterSuffix = after.slice(after.indexOf(marker));
      expect(afterSuffix).toBe(beforeSuffix);
      expect(after).toContain('description: A test assistant');
    });

    it('refuses a list item indented by four spaces instead of writing broken YAML, leaving the tree unchanged', async () => {
      const uuid = '99999999-9999-9999-9999-999999999992';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      const listFilePath = path.join(resourceDir, 'team.yaml');
      const listContent =
        '-   name: Test Assistant\n' +
        '    description: Old assistant\n' +
        '    prompt: custom/deep.prompt.md\n' +
        '    model: old-model\n';
      fs.writeFileSync(listFilePath, listContent, 'utf8');
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/team.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
          update: true,
        })
      ).rejects.toThrow(
        `Cannot safely update "Test Assistant" inside ${path.join('configs', 'imported-resources', 'assistants', 'team.yaml')}: ` +
          'its entry is indented by 4 spaces instead of 2. ' +
          `Update ${path.join('configs', 'imported-resources', 'assistants', 'team.yaml')} manually.`
      );

      expect(fs.readFileSync(listFilePath, 'utf8')).toBe(listContent);
      expect(fs.existsSync(path.join(tempDir, 'custom', 'deep.prompt.md'))).toBe(false);
    });

    it('refuses a list item that uses a merge key, leaving the tree unchanged', async () => {
      const uuid = '99999999-9999-9999-9999-999999999991';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      const listFilePath = path.join(resourceDir, 'team.yaml');
      const listContent =
        '- &base\n' +
        '  name: Base Assistant\n' +
        '  description: Shared base\n' +
        '  prompt: system_prompts/base.prompt.md\n' +
        '  model: old-model\n' +
        '- <<: *base\n' +
        '  name: Test Assistant\n';
      fs.writeFileSync(listFilePath, listContent, 'utf8');
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/team.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
          update: true,
        })
      ).rejects.toThrow('its entry uses a YAML anchor, alias or merge key');

      expect(fs.readFileSync(listFilePath, 'utf8')).toBe(listContent);
      expect(fs.existsSync(path.join(tempDir, 'system_prompts'))).toBe(false);
    });

    it('preserves a local-only key absent from the fresh platform response', async () => {
      const uuid = '99999999-9999-9999-9999-999999999997';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      fs.writeFileSync(
        path.join(resourceDir, 'test-assistant.yaml'),
        'name: Test Assistant\n' +
          'description: Old desc\n' +
          'prompt: system_prompts/test-assistant.prompt.md\n' +
          'model: old-model\n' +
          'custom_note: keep me\n',
        'utf8'
      );
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/test-assistant.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      const resourceContent = fs.readFileSync(path.join(resourceDir, 'test-assistant.yaml'), 'utf8');
      expect(resourceContent).toContain('custom_note: keep me');
    });

    it('rewrites a custom prompt path in place without creating the default prompt file', async () => {
      const uuid = '99999999-9999-9999-9999-999999999996';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      fs.writeFileSync(
        path.join(resourceDir, 'test-assistant.yaml'),
        'name: Test Assistant\n' +
          'description: Old desc\n' +
          'prompt: custom/path/for-assistant.prompt.md\n' +
          'model: old-model\n',
        'utf8'
      );
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/test-assistant.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      const customPromptPath = path.join(tempDir, 'custom', 'path', 'for-assistant.prompt.md');
      expect(fs.existsSync(customPromptPath)).toBe(true);
      expect(fs.readFileSync(customPromptPath, 'utf8')).toBe('# Test Prompt\nYou are a test assistant.');
      expect(fs.existsSync(path.join(tempDir, 'system_prompts', 'test-assistant.prompt.md'))).toBe(false);

      const resourceContent = fs.readFileSync(path.join(resourceDir, 'test-assistant.yaml'), 'utf8');
      expect(resourceContent).toContain('prompt: custom/path/for-assistant.prompt.md');
    });

    it('keeps the configured prompt path and its file untouched when the platform returns no system_prompt', async () => {
      const uuid = '99999999-9999-9999-9999-999999999993';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant', system_prompt: '' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      fs.writeFileSync(
        path.join(resourceDir, 'test-assistant.yaml'),
        'name: Test Assistant\n' +
          'description: Old desc\n' +
          'prompt: custom/path/for-assistant.prompt.md\n' +
          'model: old-model\n',
        'utf8'
      );
      const customPromptPath = path.join(tempDir, 'custom', 'path', 'for-assistant.prompt.md');
      fs.mkdirSync(path.dirname(customPromptPath), { recursive: true });
      fs.writeFileSync(customPromptPath, 'local prompt body', 'utf8');

      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/test-assistant.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      expect(fs.readFileSync(customPromptPath, 'utf8')).toBe('local prompt body');
      expect(fs.existsSync(path.join(tempDir, 'system_prompts', 'test-assistant.prompt.md'))).toBe(false);

      const resourceContent = fs.readFileSync(path.join(resourceDir, 'test-assistant.yaml'), 'utf8');
      expect(resourceContent).toContain('prompt: custom/path/for-assistant.prompt.md');
      expect(resourceContent).toContain('description: A test assistant');
    });

    it('refuses to update a resource defined inline in codemie.yaml, with no file changes', async () => {
      const uuid = '99999999-9999-9999-9999-999999999995';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      writeCodemieYaml([
        {
          name: 'Test Assistant',
          description: 'Inline assistant',
          prompt: 'system_prompts/test-assistant.prompt.md',
          model: 'old-model',
        },
      ]);
      mockConfig.resources.assistants = [{ name: 'Test Assistant' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Test Assistant', uuid, 'old prompt', {} as any);

      const beforeYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'assistant',
          slug: uuid,
          update: true,
        })
      ).rejects.toThrow(
        'Cannot update "Test Assistant": it is not defined in a file referenced by codemie.yaml. Update it manually.'
      );

      const afterYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(afterYaml).toBe(beforeYaml);
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'assistants'))).toBe(false);
    });

    it('rewrites the same file, drops the old state key, and writes the new one under the resolved name on rename', async () => {
      const uuid = '99999999-9999-9999-9999-999999999994';
      const mockAssistant = createMockAssistant({ id: uuid, name: 'Test Assistant' });

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'assistants');
      fs.mkdirSync(resourceDir, { recursive: true });
      fs.writeFileSync(
        path.join(resourceDir, 'old-name.yaml'),
        'name: Old Name\ndescription: Old desc\nprompt: system_prompts/old-name.prompt.md\nmodel: old-model\n',
        'utf8'
      );
      writeCodemieYaml([{ $import: 'configs/imported-resources/assistants/old-name.yaml' }]);
      mockConfig.resources.assistants = [{ name: 'Old Name' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateAssistantState('Old Name', uuid, 'old prompt', {} as any);

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: uuid,
        update: true,
      });

      const resourceContent = fs.readFileSync(path.join(resourceDir, 'old-name.yaml'), 'utf8');
      expect(resourceContent).toContain('name: Test Assistant');

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      const occurrences = updatedYaml.split('configs/imported-resources/assistants/old-name.yaml').length - 1;
      expect(occurrences).toBe(1);

      const statePath = path.join(tempDir, '.codemie', 'state.json');
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      expect(state.resources.assistants['Old Name']).toBeUndefined();
      expect(state.resources.assistants['Test Assistant'].id).toBe(uuid);
    });

    it('logs and imports as new when --update matches nothing in the configuration', async () => {
      const logSpy = jest.spyOn(console, 'log');
      const mockAssistant = createMockAssistant();

      const mockClient = buildAssistantClient(mockAssistant);
      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'assistant',
        slug: 'test-assistant',
        update: true,
      });

      expect(logSpy).toHaveBeenCalledWith(
        expect.stringContaining('No existing assistant found in the configuration — importing as new')
      );

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'assistants', 'test-assistant.yaml');
      expect(fs.existsSync(resourcePath)).toBe(true);

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('configs/imported-resources/assistants/test-assistant.yaml');
    });
  });

  describe('--update for workflow and datasource', () => {
    function writeCodemieYamlWith(resources: {
      assistants?: unknown[];
      datasources?: unknown[];
      workflows?: unknown[];
      skills?: unknown[];
    }): void {
      const yamlContent = yaml.stringify({
        version: '1',
        project: mockConfig.project,
        environment: mockConfig.environment,
        imported: { assistants: [], datasources: [], skills: [], integrations: [] },
        resources: {
          assistants: resources.assistants ?? [],
          datasources: resources.datasources ?? [],
          workflows: resources.workflows ?? [],
          skills: resources.skills ?? [],
        },
      });
      fs.writeFileSync(path.join(tempDir, 'codemie.yaml'), yamlContent, 'utf8');
    }

    it('rewrites a workflow definition at its custom path without creating the default one', async () => {
      const uuid = '44444444-4444-4444-4444-444444444444';
      const mockWorkflow = createMockWorkflow({ id: uuid, name: 'Test Workflow' });

      const configDir = path.join(tempDir, 'configs', 'workflows');
      fs.mkdirSync(configDir, { recursive: true });
      fs.writeFileSync(
        path.join(configDir, 'test-workflow.yaml'),
        'name: Test Workflow\ndescription: Old desc\ndefinition: custom/wf-definition.yaml\nmode: Sequential\n',
        'utf8'
      );
      writeCodemieYamlWith({ workflows: [{ $import: 'configs/workflows/test-workflow.yaml' }] });
      mockConfig.resources.workflows = [{ name: 'Test Workflow' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateWorkflowState('Test Workflow', uuid, 'old-checksum', 'old-config-checksum');

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn().mockResolvedValue(mockWorkflow) },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'workflow',
        slug: uuid,
        update: true,
      });

      const customDefPath = path.join(tempDir, 'custom', 'wf-definition.yaml');
      expect(fs.readFileSync(customDefPath, 'utf8')).toBe('assistants:\n  - name: test\n');
      expect(fs.existsSync(path.join(tempDir, 'workflows', 'test-workflow.yaml'))).toBe(false);

      const resourceContent = fs.readFileSync(path.join(configDir, 'test-workflow.yaml'), 'utf8');
      expect(resourceContent).toContain('definition: custom/wf-definition.yaml');
      expect(resourceContent).toContain('description: A test workflow');

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml.split('configs/workflows/test-workflow.yaml').length - 1).toBe(1);

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8'));
      expect(state.resources.workflows['Test Workflow'].id).toBe(uuid);
      expect(state.resources.workflows['Test Workflow'].workflowYamlChecksum).not.toBe('old-checksum');
      expect(state.resources.workflows['Test Workflow'].workflowYamlChecksum).toBeTruthy();
    });

    it('rewrites a project skill from resources.skills at its custom file path, not via imported.skills', async () => {
      const mockSkill = createMockSkill({ description: 'Fresh description' });

      const configDir = path.join(tempDir, 'configs', 'skills');
      fs.mkdirSync(configDir, { recursive: true });
      fs.writeFileSync(
        path.join(configDir, 'test-skill.yaml'),
        'name: Test Skill\ndescription: Old desc\nfile: custom/test-skill.md\nmy_local_field: keep-me\n',
        'utf8'
      );
      fs.mkdirSync(path.join(tempDir, 'custom'), { recursive: true });
      fs.writeFileSync(path.join(tempDir, 'custom', 'test-skill.md'), 'old body', 'utf8');
      writeCodemieYamlWith({ skills: [{ $import: 'configs/skills/test-skill.yaml' }] });
      mockConfig.resources.skills = [{ name: 'Test Skill' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateSkillState('Test Skill', 'sk-123', 'old body', { name: 'Test Skill' } as any);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest.fn().mockResolvedValue([]),
          getCompanionFile: jest.fn(),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
        update: true,
      });

      expect(fs.readFileSync(path.join(tempDir, 'custom', 'test-skill.md'), 'utf8')).toBe(mockSkill.content);
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill.skill.md'))).toBe(false);

      const resourceContent = fs.readFileSync(path.join(configDir, 'test-skill.yaml'), 'utf8');
      expect(resourceContent).toContain('file: custom/test-skill.md');
      expect(resourceContent).toContain('description: Fresh description');
      expect(resourceContent).toContain('my_local_field: keep-me');

      const updatedYaml = yaml.parse(fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8'));
      expect(updatedYaml.resources.skills).toEqual([{ $import: 'configs/skills/test-skill.yaml' }]);
      expect(updatedYaml.imported.skills).toEqual([]);

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8'));
      expect(state.resources.skills['Test Skill'].id).toBe('sk-123');
    });

    it('defaults an updated skill with companion files to skills/<name>/SKILL.md when no file path was configured', async () => {
      const mockSkill = createMockSkill({
        description: 'Fresh description',
        companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 }],
      });

      const configDir = path.join(tempDir, 'configs', 'skills');
      fs.mkdirSync(configDir, { recursive: true });
      fs.writeFileSync(path.join(configDir, 'test-skill.yaml'), 'name: Test Skill\ndescription: Old desc\n', 'utf8');
      writeCodemieYamlWith({ skills: [{ $import: 'configs/skills/test-skill.yaml' }] });
      mockConfig.resources.skills = [{ name: 'Test Skill' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateSkillState('Test Skill', 'sk-123', 'old body', { name: 'Test Skill' } as any);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([
              { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 },
            ]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: 'reference.md',
            content: 'reference body',
            mime_type: 'text/markdown',
            encoding: 'text',
            size_bytes: 14,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
        update: true,
      });

      expect(fs.readFileSync(path.join(tempDir, 'skills', 'test-skill', 'SKILL.md'), 'utf8')).toBe(mockSkill.content);
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill.skill.md'))).toBe(false);

      const resourceContent = fs.readFileSync(path.join(configDir, 'test-skill.yaml'), 'utf8');
      expect(resourceContent).toContain('file: skills/test-skill/SKILL.md');
    });

    it('refreshes companion file bodies on disk under --update', async () => {
      const mockSkill = createMockSkill({ description: 'Fresh description' });

      const configDir = path.join(tempDir, 'configs', 'skills');
      fs.mkdirSync(configDir, { recursive: true });
      fs.writeFileSync(
        path.join(configDir, 'test-skill.yaml'),
        'name: Test Skill\ndescription: Old desc\nfile: skills/test-skill/SKILL.md\n',
        'utf8'
      );
      fs.mkdirSync(path.join(tempDir, 'skills', 'test-skill'), { recursive: true });
      fs.writeFileSync(path.join(tempDir, 'skills', 'test-skill', 'reference.md'), 'stale body', 'utf8');
      writeCodemieYamlWith({ skills: [{ $import: 'configs/skills/test-skill.yaml' }] });
      mockConfig.resources.skills = [{ name: 'Test Skill' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateSkillState('Test Skill', 'sk-123', 'old body', { name: 'Test Skill' } as any);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([
              { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 },
            ]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: 'reference.md',
            content: 'fresh body',
            mime_type: 'text/markdown',
            encoding: 'text',
            size_bytes: 10,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
        update: true,
      });

      expect(fs.readFileSync(path.join(tempDir, 'skills', 'test-skill', 'reference.md'), 'utf8')).toBe('fresh body');
      expect(fs.readFileSync(path.join(tempDir, 'skills', 'test-skill', 'SKILL.md'), 'utf8')).toBe(mockSkill.content);
    });

    it('does not record companion hashes when the configured entry is flat but the platform skill has companions', async () => {
      const warnSpy = jest.spyOn(logger, 'warn').mockImplementation();
      const mockSkill = createMockSkill({ description: 'Fresh description' });

      const configDir = path.join(tempDir, 'configs', 'skills');
      fs.mkdirSync(configDir, { recursive: true });
      fs.writeFileSync(
        path.join(configDir, 'test-skill.yaml'),
        'name: Test Skill\ndescription: Old desc\nfile: skills/test-skill.skill.md\n',
        'utf8'
      );
      fs.mkdirSync(path.join(tempDir, 'skills'), { recursive: true });
      fs.writeFileSync(path.join(tempDir, 'skills', 'test-skill.skill.md'), 'stale body', 'utf8');
      writeCodemieYamlWith({ skills: [{ $import: 'configs/skills/test-skill.yaml' }] });
      mockConfig.resources.skills = [{ name: 'Test Skill' } as SkillResource];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateSkillState('Test Skill', 'sk-123', 'old body', { name: 'Test Skill' } as SkillResource);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([
              { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 },
            ]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: 'reference.md',
            content: 'reference body',
            mime_type: 'text/markdown',
            encoding: 'text',
            size_bytes: 14,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
        update: true,
      });

      // The flat content file is still refreshed, and the layout is left exactly as configured.
      expect(fs.readFileSync(path.join(tempDir, 'skills', 'test-skill.skill.md'), 'utf8')).toBe(mockSkill.content);
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill'))).toBe(false);
      expect(fs.readFileSync(path.join(configDir, 'test-skill.yaml'), 'utf8')).toContain(
        'file: skills/test-skill.skill.md'
      );

      // Nothing was written to disk, so state must not claim the companions are managed locally —
      // recorded hashes would make the next deploy send `companion_files: []` and delete them.
      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8'));
      expect(state.resources.skills['Test Skill'].companionFileHashes).toBeUndefined();
      expect(state.resources.skills['Test Skill'].companionFilesChecksum).toBeUndefined();

      const warnings = warnSpy.mock.calls.map((call) => String(call[0])).join('\n');
      expect(warnings).toContain('Test Skill');
      expect(warnings).toContain('SKILL.md');
    });

    it('re-imports a datasource in place with no companion file and no second $import', async () => {
      const mockDatasource = createMockDatasource();

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'datasources');
      fs.mkdirSync(resourceDir, { recursive: true });
      const resourceFilePath = path.join(resourceDir, 'test-repo.yaml');
      fs.writeFileSync(
        resourceFilePath,
        'name: test-repo\ntype: code\ndescription: Old desc\ncustom_note: keep me\n',
        'utf8'
      );
      writeCodemieYamlWith({ datasources: [{ $import: 'configs/imported-resources/datasources/test-repo.yaml' }] });
      mockConfig.resources.datasources = [{ name: 'test-repo' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateDatasourceState('test-repo', 'ds-123', {} as any);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: {
          list: jest.fn().mockResolvedValue([{ id: 'ds-123', name: 'test-repo' }]),
          get: jest.fn().mockResolvedValue(mockDatasource),
        },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'datasource',
        slug: 'test-repo',
        update: true,
      });

      const resourceContent = fs.readFileSync(resourceFilePath, 'utf8');
      expect(resourceContent).toContain('description: A test datasource');
      expect(resourceContent).toContain('custom_note: keep me');

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml.split('configs/imported-resources/datasources/test-repo.yaml').length - 1).toBe(1);

      expect(fs.readdirSync(resourceDir)).toEqual(['test-repo.yaml']);

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8'));
      expect(state.resources.datasources['test-repo'].id).toBe('ds-123');
    });

    it('moves the datasource state entry to the new name when the platform renamed it', async () => {
      const mockDatasource = createMockDatasource();

      const resourceDir = path.join(tempDir, 'configs', 'imported-resources', 'datasources');
      fs.mkdirSync(resourceDir, { recursive: true });
      const resourceFilePath = path.join(resourceDir, 'old-repo.yaml');
      fs.writeFileSync(resourceFilePath, 'name: old-repo\ntype: code\ndescription: Old desc\n', 'utf8');
      writeCodemieYamlWith({ datasources: [{ $import: 'configs/imported-resources/datasources/old-repo.yaml' }] });
      mockConfig.resources.datasources = [{ name: 'old-repo' } as any];

      const stateManager = new StateManager(mockAppConfig);
      stateManager.updateDatasourceState('old-repo', 'ds-123', {} as any);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: {
          list: jest.fn().mockResolvedValue([{ id: 'ds-123', name: 'test-repo' }]),
          get: jest.fn().mockResolvedValue(mockDatasource),
        },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'datasource',
        slug: 'test-repo',
        update: true,
      });

      const resourceContent = fs.readFileSync(resourceFilePath, 'utf8');
      expect(resourceContent).toContain('name: test-repo');

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8'));
      expect(state.resources.datasources['old-repo']).toBeUndefined();
      expect(state.resources.datasources['test-repo'].id).toBe('ds-123');
    });
  });

  describe('Datasource import', () => {
    it('should import datasource by name', async () => {
      const mockDatasource = createMockDatasource();

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: {
          list: jest.fn().mockResolvedValue([{ id: 'ds-123', name: 'test-repo' }]),
          get: jest.fn().mockResolvedValue(mockDatasource),
        },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'datasource',
        slug: 'test-repo',
      });

      // Verify resource YAML was created
      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'datasources', 'test-repo.yaml');
      expect(fs.existsSync(resourcePath)).toBe(true);

      const resourceContent = yaml.parse(fs.readFileSync(resourcePath, 'utf8'));
      expect(resourceContent.name).toBe('test-repo');
      expect(resourceContent.type).toBe('code');

      // Verify codemie.yaml was updated
      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('configs/imported-resources/datasources/test-repo.yaml');

      // Verify state was updated
      const statePath = path.join(tempDir, '.codemie', 'state.json');
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      expect(state.resources.datasources['test-repo']).toBeDefined();
      expect(state.resources.datasources['test-repo'].id).toBe('ds-123');
    });

    it('should resolve integration alias in datasource setting_id', async () => {
      const mockDatasource = createMockDatasource({ setting_id: 'int-123' });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: {
          list: jest.fn().mockResolvedValue([{ id: 'ds-123', name: 'test-repo' }]),
          get: jest.fn().mockResolvedValue(mockDatasource),
        },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'datasource',
        slug: 'test-repo',
      });

      const resourcePath = path.join(tempDir, 'configs', 'imported-resources', 'datasources', 'test-repo.yaml');
      const resourceContent = yaml.parse(fs.readFileSync(resourcePath, 'utf8'));
      expect(resourceContent.setting_id).toBe('$ref:imported.integrations.my-git.id');
    });
  });

  describe('Workflow import', () => {
    it('should import a workflow by UUID', async () => {
      const uuid = '33333333-3333-3333-3333-333333333333';
      const mockWorkflow = createMockWorkflow({ id: uuid });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: {
          list: jest.fn(),
          get: jest.fn().mockResolvedValue(mockWorkflow),
        },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'workflow',
        slug: uuid,
      });

      expect(mockClient.workflows.get).toHaveBeenCalledWith(uuid);
      expect(mockClient.workflows.list).not.toHaveBeenCalled();

      const resourcePath = path.join(tempDir, 'configs', 'workflows', 'test-workflow.yaml');
      expect(fs.existsSync(resourcePath)).toBe(true);
    });

    it('omits the definition key on a new import when the platform returns no yaml_config', async () => {
      const mockWorkflow = createMockWorkflow({ yaml_config: '' });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: {
          list: jest.fn().mockResolvedValue([{ id: 'wf-123', name: 'Test Workflow' }]),
          get: jest.fn().mockResolvedValue(mockWorkflow),
        },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'workflow',
        slug: 'Test Workflow',
      });

      expect(fs.existsSync(path.join(tempDir, 'workflows', 'test-workflow.yaml'))).toBe(false);

      const resourceContent = yaml.parse(
        fs.readFileSync(path.join(tempDir, 'configs', 'workflows', 'test-workflow.yaml'), 'utf8')
      );
      expect(resourceContent.definition).toBeUndefined();
    });

    it('should import workflow by name', async () => {
      const mockWorkflow = createMockWorkflow();

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: {
          list: jest.fn().mockResolvedValue([{ id: 'wf-123', name: 'Test Workflow' }]),
          get: jest.fn().mockResolvedValue(mockWorkflow),
        },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'workflow',
        slug: 'Test Workflow',
      });

      // Verify workflow definition file was created
      expect(fs.existsSync(path.join(tempDir, 'workflows', 'test-workflow.yaml'))).toBe(true);
      const workflowContent = fs.readFileSync(path.join(tempDir, 'workflows', 'test-workflow.yaml'), 'utf8');
      expect(workflowContent).toBe('assistants:\n  - name: test\n');

      // Verify resource YAML was created
      const resourcePath = path.join(tempDir, 'configs', 'workflows', 'test-workflow.yaml');
      expect(fs.existsSync(resourcePath)).toBe(true);

      // Verify codemie.yaml was updated
      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('configs/workflows/test-workflow.yaml');
    });
  });

  describe('Skill import', () => {
    it('should import project-owned skill into resources.skills with content file', async () => {
      const mockSkill = createMockSkill();

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest.fn().mockResolvedValue([]),
          getCompanionFile: jest.fn(),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
      });

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('resources:');
      expect(updatedYaml).toContain('configs/imported-resources/skills/test-skill.yaml');
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill.skill.md'))).toBe(true);
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'skills', 'test-skill.yaml'))).toBe(
        true
      );

      const statePath = path.join(tempDir, '.codemie', 'state.json');
      expect(fs.existsSync(statePath)).toBe(true);
      const state = JSON.parse(fs.readFileSync(statePath, 'utf8')) as {
        resources: { skills: Record<string, { id: string }> };
      };
      expect(state.resources.skills['Test Skill']?.id).toBe('sk-123');
    });

    it('imports a project-owned skill with companion files into skills/<name>/SKILL.md', async () => {
      const mockSkill = createMockSkill({
        companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 }],
      });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([
              { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 },
            ]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: 'reference.md',
            content: 'reference body',
            mime_type: 'text/markdown',
            encoding: 'text',
            size_bytes: 14,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
      });

      expect(fs.readFileSync(path.join(tempDir, 'skills', 'test-skill', 'SKILL.md'), 'utf8')).toBe(mockSkill.content);
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill.skill.md'))).toBe(false);

      const resourceYaml = fs.readFileSync(
        path.join(tempDir, 'configs', 'imported-resources', 'skills', 'test-skill.yaml'),
        'utf8'
      );
      expect(resourceYaml).toContain('file: skills/test-skill/SKILL.md');
    });

    it('writes a punctuated skill name to the path its resource YAML references', async () => {
      const mockSkill = createMockSkill({
        id: 'sk-punct',
        name: 'C++ Helper',
        companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 14 }],
      });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-punct', name: 'C++ Helper' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([
              { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 14 },
            ]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: 'reference.md',
            content: 'reference body',
            mime_type: 'text/markdown',
            encoding: 'text',
            size_bytes: 14,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'C++ Helper',
      });

      const resourceYaml = fs.readFileSync(
        path.join(tempDir, 'configs', 'imported-resources', 'skills', 'c-helper.yaml'),
        'utf8'
      );
      const referenced = /file:\s*(\S+)/.exec(resourceYaml)?.[1];

      expect(referenced).toBe('skills/c-helper/SKILL.md');
      expect(fs.existsSync(path.join(tempDir, referenced as string))).toBe(true);
      expect(fs.readFileSync(path.join(tempDir, 'skills', 'c-helper', 'reference.md'), 'utf8')).toBe('reference body');
    });

    it('refuses a companion path escaping the skill directory and writes nothing outside it', async () => {
      const mockSkill = createMockSkill({
        companion_files: [{ path: '../escape.txt', mime_type: 'text/plain', encoding: 'text', size_bytes: 5 }],
      });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest
            .fn()
            .mockResolvedValue([{ path: '../escape.txt', mime_type: 'text/plain', encoding: 'text', size_bytes: 5 }]),
          getCompanionFile: jest.fn().mockResolvedValue({
            path: '../escape.txt',
            content: 'pwned',
            mime_type: 'text/plain',
            encoding: 'text',
            size_bytes: 5,
          }),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      // A hostile path on a single named resource aborts the import loudly.
      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'skill',
          slug: 'Test Skill',
        })
      ).rejects.toThrow(/\.\.\/escape\.txt/);

      const escapedFiles: string[] = [];
      const collect = (dir: string): void => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            collect(full);
            continue;
          }
          if (entry.name === 'escape.txt') {
            escapedFiles.push(full);
          }
        }
      };
      collect(tempDir);

      expect(escapedFiles).toEqual([]);
    });

    it('writes every companion file correctly when the fetches resolve out of order', async () => {
      const mockSkill = createMockSkill();
      const metadata = [
        { path: 'a.md', mime_type: 'text/markdown', encoding: 'text' as const, size_bytes: 1 },
        { path: 'nested/b.md', mime_type: 'text/markdown', encoding: 'text' as const, size_bytes: 1 },
        { path: 'c.md', mime_type: 'text/markdown', encoding: 'text' as const, size_bytes: 1 },
        { path: 'd.md', mime_type: 'text/markdown', encoding: 'text' as const, size_bytes: 1 },
      ];
      // Later paths resolve first, so a writer that relied on fetch order would mix up bodies.
      const delays: Record<string, number> = { 'a.md': 40, 'nested/b.md': 30, 'c.md': 20, 'd.md': 0 };

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest.fn().mockResolvedValue(metadata),
          getCompanionFile: jest.fn().mockImplementation(
            (_id: string, filePath: string) =>
              new Promise((resolve) => {
                setTimeout(
                  () =>
                    resolve({
                      path: filePath,
                      content: `body of ${filePath}`,
                      mime_type: 'text/markdown',
                      encoding: 'text',
                      size_bytes: 1,
                    }),
                  delays[filePath]
                );
              })
          ),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
      });

      for (const entry of metadata) {
        const written = fs.readFileSync(path.join(tempDir, 'skills', 'test-skill', ...entry.path.split('/')), 'utf8');
        expect(written).toBe(`body of ${entry.path}`);
      }

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8')) as {
        resources: { skills: Record<string, { companionFileHashes?: Record<string, string> }> };
      };
      expect(Object.keys(state.resources.skills['Test Skill']?.companionFileHashes ?? {}).sort()).toEqual([
        'a.md',
        'c.md',
        'd.md',
        'nested/b.md',
      ]);
    });

    it('writes companion file bodies next to SKILL.md and records them in state', async () => {
      // skills.get() carries companion metadata at best, so the authoritative list comes from
      // listCompanionFiles — this mock deliberately omits companion_files from the get response.
      const mockSkill = createMockSkill();
      const binaryBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x00, 0x01]);

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
          listCompanionFiles: jest.fn().mockResolvedValue([
            { path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 14 },
            { path: 'assets/logo.png', mime_type: 'image/png', encoding: 'base64', size_bytes: 6 },
          ]),
          getCompanionFile: jest.fn(async (_id: string, filePath: string) =>
            filePath === 'reference.md'
              ? {
                  path: 'reference.md',
                  content: 'reference body',
                  mime_type: 'text/markdown',
                  encoding: 'text',
                  size_bytes: 14,
                }
              : {
                  path: 'assets/logo.png',
                  content: binaryBytes.toString('base64'),
                  mime_type: 'image/png',
                  encoding: 'base64',
                  size_bytes: binaryBytes.length,
                }
          ),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
      });

      const skillDir = path.join(tempDir, 'skills', 'test-skill');
      expect(fs.readFileSync(path.join(skillDir, 'SKILL.md'), 'utf8')).toBe(mockSkill.content);
      expect(fs.readFileSync(path.join(skillDir, 'reference.md'), 'utf8')).toBe('reference body');
      expect(fs.readFileSync(path.join(skillDir, 'assets', 'logo.png'))).toEqual(binaryBytes);

      const state = JSON.parse(fs.readFileSync(path.join(tempDir, '.codemie', 'state.json'), 'utf8')) as {
        resources: { skills: Record<string, { companionFileHashes?: Record<string, string> }> };
      };
      expect(Object.keys(state.resources.skills['Test Skill']?.companionFileHashes ?? {}).sort()).toEqual([
        'assets/logo.png',
        'reference.md',
      ]);
    });

    it('should import external skill into imported.skills without content file', async () => {
      const mockSkill = createMockSkill({ project: 'other-project' });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
      });

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('imported:');
      expect(updatedYaml).toContain('name: Test Skill');
      expect(updatedYaml).toContain('id: sk-123');
      expect(fs.existsSync(path.join(tempDir, 'skills', 'test-skill.skill.md'))).toBe(false);
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'skills'))).toBe(false);

      const statePath = path.join(tempDir, '.codemie', 'state.json');
      expect(fs.existsSync(statePath)).toBe(false);
    });

    it('logs the importing-as-new line when --update finds no imported.skills entry to refresh', async () => {
      const logSpy = jest.spyOn(console, 'log');
      const mockSkill = createMockSkill({ project: 'other-project' });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'Test Skill',
        update: true,
      });

      expect(logSpy).toHaveBeenCalledWith(
        expect.stringContaining('No existing skill found in the configuration — importing as new')
      );

      const updatedYaml = yaml.parse(fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8')) as CodemieConfig;
      expect(updatedYaml.imported.skills).toEqual([{ name: 'Test Skill', id: 'sk-123' }]);
    });

    it('should reject importing a skill that already exists in imported.skills', async () => {
      const existingConfig = createMockConfig();
      existingConfig.imported.skills = [{ name: 'Test Skill', id: 'sk-existing' }];
      MockedConfigLoader.mockImplementation(
        () =>
          ({
            loadConfig: jest.fn().mockReturnValue(existingConfig),
          }) as unknown as CodemieConfigLoader
      );

      const mockSkill = createMockSkill();
      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-123', name: 'Test Skill' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'skill',
          slug: 'Test Skill',
        })
      ).rejects.toThrow('already exists in the configuration');
    });

    it('should refresh a stale imported.skills entry name and id under --update, preserving comments', async () => {
      mockConfig.imported.skills = [{ name: 'Old Skill Name', id: 'sk-external' }];

      const codemieYamlWithComment = `version: '1'
project:
  name: test-project
  description: Test
environment:
  codemie_api_url: https://api.example.com
  auth_server_url: https://auth.example.com
  auth_realm_name: test
  client_id: test-client
  client_secret: secret
imported:
  assistants: []
  datasources: []
  skills:
    - name: Old Skill Name # stale name before platform rename
      id: sk-external
  integrations: []
resources:
  assistants: []
  datasources: []
  workflows: []
  skills: []
`;
      fs.writeFileSync(path.join(tempDir, 'codemie.yaml'), codemieYamlWithComment, 'utf8');

      const mockSkill = createMockSkill({ id: 'sk-external', name: 'New Skill Name', project: 'other-project' });

      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: { list: jest.fn(), get: jest.fn() },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: {
          list: jest.fn().mockResolvedValue([{ id: 'sk-external', name: 'New Skill Name' }]),
          get: jest.fn().mockResolvedValue(mockSkill),
        },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await importResource({
        appConfig: mockAppConfig,
        resourceType: 'skill',
        slug: 'New Skill Name',
        update: true,
      });

      const updatedYaml = fs.readFileSync(path.join(tempDir, 'codemie.yaml'), 'utf8');
      expect(updatedYaml).toContain('# stale name before platform rename');
      expect(updatedYaml).toContain('name: New Skill Name');
      expect(updatedYaml).toContain('id: sk-external');
      expect(updatedYaml).not.toContain('Old Skill Name');
      expect(updatedYaml).not.toContain('skill_ids');

      expect(fs.existsSync(path.join(tempDir, 'skills'))).toBe(false);
      expect(fs.existsSync(path.join(tempDir, 'configs', 'imported-resources', 'skills'))).toBe(false);

      const statePath = path.join(tempDir, '.codemie', 'state.json');
      expect(fs.existsSync(statePath)).toBe(false);
    });
  });

  describe('Resource not found', () => {
    it('should throw error when datasource not found on platform', async () => {
      const mockClient = {
        assistants: { getBySlug: jest.fn(), get: jest.fn(), list: jest.fn() },
        datasources: {
          list: jest.fn().mockResolvedValue([]),
          get: jest.fn(),
        },
        workflows: { list: jest.fn(), get: jest.fn() },
        skills: { list: jest.fn(), get: jest.fn() },
        integrations: { list: jest.fn() },
      } as unknown as CodeMieClient;

      mockCreateClient.mockResolvedValue(mockClient);

      await expect(
        importResource({
          appConfig: mockAppConfig,
          resourceType: 'datasource',
          slug: 'nonexistent-ds',
        })
      ).rejects.toThrow('datasource "nonexistent-ds" not found on platform');
    });
  });

  describe('main() CLI entry', () => {
    it('should set process.exitCode on failure', async () => {
      MockedConfigLoader.mockImplementation(
        () =>
          ({
            loadConfig: jest.fn().mockImplementation(() => {
              throw new Error('Config not found');
            }),
          }) as unknown as CodemieConfigLoader
      );

      await main({
        appConfig: mockAppConfig,
        resourceType: 'datasource',
        slug: 'test',
      });

      expect(process.exitCode).toBe(1);
    });
  });
});
