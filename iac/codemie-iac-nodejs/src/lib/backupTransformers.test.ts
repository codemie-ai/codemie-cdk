/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { MCPServerDetails, ToolDetails, ToolKitDetails } from 'codemie-sdk';

import {
  transformMcpServer,
  transformTool,
  transformToolkits,
  collectReferencedSkillIds,
  partitionSkillsForBackupYaml,
  prepareAssistantForYaml,
  prepareImportedSkillForYaml,
  prepareSkillForYaml,
} from './backupTransformers';
import { calculateChecksum } from './checksumUtils';
import { calculateCompanionFilesChecksum } from './codemieConfigChecksums';
import { collectCompanionFiles } from './skillCompanionFiles';
import { isProjectOwnedSkill } from './skillUtils';
import type { AssistantResponse } from './converters';
import type { StateFile } from '../types/codemieConfig';
import { createMockAssistant, createMockSkill } from '../testFixtures';

describe('backupTransformers', () => {
  describe('transformTool', () => {
    it('should transform tool with integration settings to use $ref', () => {
      const integrationMap = new Map<string, string>([['int-123', 'Jira Server Connection']]);
      const tool: ToolDetails = {
        name: 'jira_get_issue',
        label: 'Get Jira Issue',
        settings_config: false,
        settings: {
          id: 'int-123',
          project_name: 'test-project',
          alias: 'Jira Server Connection',
          credential_type: 'Jira',
          credential_values: [{ key: 'url', value: 'https://jira.example.com' }],
          setting_type: 'project',
        },
      };

      const result = transformTool(tool, integrationMap);

      expect(result.name).toBe('jira_get_issue');
      expect(result.label).toBe('Get Jira Issue');
      expect(result.settings).toEqual({ $ref: 'imported.integrations.Jira Server Connection' });
    });

    it('should use alias from map if not present in settings', () => {
      const integrationMap = new Map<string, string>([['int-456', 'GitLab Connection']]);
      const tool: ToolDetails = {
        name: 'gitlab_get_file',
        settings_config: true,
        settings: {
          id: 'int-456',
          project_name: 'test-project',
          credential_type: 'Git',
          credential_values: [],
          setting_type: 'project',
        },
      };

      const result = transformTool(tool, integrationMap);

      expect(result.name).toBe('gitlab_get_file');
      expect(result.settings).toEqual({ $ref: 'imported.integrations.GitLab Connection' });
    });

    it('should skip null label', () => {
      const integrationMap = new Map<string, string>();
      const tool: ToolDetails = {
        name: 'test_tool',
        label: null as unknown as string,
        settings_config: false,
      };

      const result = transformTool(tool, integrationMap);

      expect(result.name).toBe('test_tool');
      expect(result.label).toBeUndefined();
    });

    it('should keep settings if no alias found', () => {
      const integrationMap = new Map<string, string>();
      const tool: ToolDetails = {
        name: 'unknown_tool',
        settings_config: false,
        settings: {
          id: 'int-999',
          project_name: 'test-project',
          credential_type: 'OpenAPI',
          credential_values: [],
          setting_type: 'project',
        },
      };

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();
      const result = transformTool(tool, integrationMap);

      expect(result.settings).toEqual(tool.settings);
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('No alias found for tool int-999'));
      consoleSpy.mockRestore();
    });

    it('should extract OpenAPI spec to file reference when no alias found', () => {
      const integrationMap = new Map<string, string>();
      const integrationSpecPaths = new Map<string, string>();
      const largeOpenApiSpec = JSON.stringify({
        openapi: '3.0.0',
        info: { title: 'Coda API', version: '1.0.0' },
        paths: {
          '/docs': { get: { summary: 'Get docs' } },
          '/tables': { get: { summary: 'Get tables' } },
        },
      });

      const tool: ToolDetails = {
        name: 'coda_tool',
        settings_config: false,
        settings: {
          id: 'int-coda-123',
          project_name: 'test-project',
          credential_type: 'OpenAPI',
          credential_values: [
            { key: 'url', value: 'https://coda.io/api' },
            { key: 'openapi_spec', value: largeOpenApiSpec },
          ],
          setting_type: 'project',
        },
      };

      integrationSpecPaths.set('int-coda-123', 'openapi_specs/coda-api.json');

      const result = transformTool(tool, integrationMap, integrationSpecPaths);

      expect(result.settings).toBeDefined();
      expect(result.settings && '$ref' in result.settings).toBe(false);

      const settings = result.settings as { credential_values?: Array<{ key: string; value: unknown }> };
      expect(settings.credential_values).toBeDefined();

      const openapiSpecValue = settings.credential_values?.find((cv) => cv.key === 'openapi_spec');
      expect(openapiSpecValue?.value).toBe('openapi_specs/coda-api.json');

      const urlValue = settings.credential_values?.find((cv) => cv.key === 'url');
      expect(urlValue?.value).toBe('https://coda.io/api');
    });

    it('should handle tool without settings', () => {
      const integrationMap = new Map<string, string>();
      const tool: ToolDetails = {
        name: 'simple_tool',
        settings_config: false,
      };

      const result = transformTool(tool, integrationMap);

      expect(result.name).toBe('simple_tool');
      expect(result.settings).toBeUndefined();
    });
  });

  describe('transformMcpServer', () => {
    it('should preserve saved-config MCP fields when transforming for backup', () => {
      const mcp: MCPServerDetails = {
        name: 'RI-logs',
        description: 'Download, unzip and grep log files',
        enabled: true,
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        integration_alias: 'ri-logs-alias',
        use_custom_config: true,
        resolve_dynamic_values_in_arguments: false,
        tools: ['fetch_logs'],
        config: {
          url: 'https://mcp.example.com/mcp',
          headers: { Authorization: 'Bearer token' },
          type: 'streamable-http',
          single_usage: true,
          tools: ['config-tool-a'],
        },
      };

      const result = transformMcpServer(mcp, new Map());

      expect(result).toMatchObject({
        name: 'RI-logs',
        description: 'Download, unzip and grep log files',
        enabled: true,
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        integration_alias: 'ri-logs-alias',
        use_custom_config: true,
        resolve_dynamic_values_in_arguments: false,
        tools: ['fetch_logs'],
        config: {
          url: 'https://mcp.example.com/mcp',
          headers: { Authorization: 'Bearer token' },
          type: 'streamable-http',
          single_usage: true,
          tools: ['config-tool-a'],
        },
      });
    });

    it('should pass through a field the transformer does not enumerate', () => {
      const mcp = {
        name: 'RI-logs',
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        // A saved-config key the transformer has no explicit branch for
        saved_config_revision: 7,
      } as unknown as MCPServerDetails;

      const result = transformMcpServer(mcp, new Map()) as unknown as Record<string, unknown>;

      expect(result.saved_config_revision).toBe(7);
      expect(result.mcp_config_id).toBe('a6395977-3598-4a0a-bfb3-08463d484575');
    });

    it('should drop null-valued keys and an empty mcp_connect_url', () => {
      const mcp = {
        name: 'Figma MCP',
        description: 'Figma integration',
        enabled: true,
        command: 'npx',
        arguments: '-y figma-developer-mcp --stdio',
        config: null,
        mcp_connect_url: '',
        tools_tokens_size_limit: null,
        mcp_config_id: null,
        mcp_connect_auth_token: null,
      } as unknown as MCPServerDetails;

      const result = transformMcpServer(mcp, new Map()) as unknown as Record<string, unknown>;

      expect(result).not.toHaveProperty('config');
      expect(result).not.toHaveProperty('mcp_connect_url');
      expect(result).not.toHaveProperty('tools_tokens_size_limit');
      expect(result).not.toHaveProperty('mcp_config_id');
      expect(result).not.toHaveProperty('mcp_connect_auth_token');
      expect(result).toMatchObject({ name: 'Figma MCP', command: 'npx', enabled: true });
    });

    it('should keep resolving settings and mcp_connect_auth_token to $ref', () => {
      const mcp = {
        name: 'Figma MCP',
        settings: { id: 'int-settings-1', name: 'Figma_Codemie', credential_type: 'MCP' },
        mcp_connect_auth_token: { id: 'int-auth-1', name: 'MCP Auth', credential_type: 'Bearer' },
      } as unknown as MCPServerDetails;
      const aliasMap = new Map<string, string>([
        ['int-settings-1', 'mock_mcp'],
        ['int-auth-1', 'mcp_auth_bearer'],
      ]);

      const result = transformMcpServer(mcp, aliasMap);

      expect(result.settings).toEqual({ $ref: 'imported.integrations.mock_mcp' });
      expect(result.mcp_connect_auth_token).toEqual({ $ref: 'imported.integrations.mcp_auth_bearer' });
    });
  });

  describe('prepareAssistantForYaml', () => {
    it.each([
      [['search_kb'], true],
      [[], false],
      [undefined, false],
    ])('handles deselected_default_tools %p', (tools, present) => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: { assistants: {}, datasources: {}, workflows: {}, skills: {} },
      };
      const assistant = {
        id: 'ast-1',
        name: 'A',
        description: 'd',
        system_prompt: 'p',
        llm_model_type: 'gpt-4',
        deselected_default_tools: tools,
      } as unknown as AssistantResponse;

      const result = prepareAssistantForYaml(assistant, state, new Map(), new Map());

      if (present) {
        expect(result.deselected_default_tools).toEqual(tools);
      } else {
        expect(result).not.toHaveProperty('deselected_default_tools');
      }
    });

    it('should preserve config-id-only MCP servers in backup resource', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const assistant: AssistantResponse = {
        id: 'ast-123',
        name: 'Test Assistant',
        description: 'Test',
        system_prompt: 'You are helpful',
        system_prompt_history: [],
        project: 'test-project',
        llm_model_type: 'gpt-4',
        context: [],
        toolkits: [],
        conversation_starters: [],
        assistant_ids: [],
        mcp_servers: [
          {
            name: 'RI-logs',
            description: 'Download, unzip and grep log files',
            enabled: true,
            mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
            resolve_dynamic_values_in_arguments: false,
            tools: ['fetch_logs'],
          },
        ],
        nested_assistants: [],
        creator: 'user-1',
        shared: false,
        is_react: false,
        is_global: false,
      } as AssistantResponse;

      const result = prepareAssistantForYaml(assistant, state, new Map(), new Map());

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0]).toMatchObject({
        name: 'RI-logs',
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        resolve_dynamic_values_in_arguments: false,
        tools: ['fetch_logs'],
      });
      expect(state.resources.assistants['Test Assistant']).toBeDefined();
    });
    it('should write MCP servers free of null keys into the backup resource', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const assistant = {
        id: 'ast-456',
        name: 'Figma Assistant',
        description: 'Test',
        system_prompt: 'You are helpful',
        system_prompt_history: [],
        project: 'test-project',
        llm_model_type: 'gpt-4',
        context: [],
        toolkits: [],
        conversation_starters: [],
        assistant_ids: [],
        mcp_servers: [
          {
            name: 'Figma MCP',
            description: 'Figma integration',
            enabled: true,
            command: 'npx',
            arguments: '-y figma-developer-mcp --stdio',
            config: null,
            mcp_connect_url: '',
            tools_tokens_size_limit: null,
            mcp_connect_auth_token: null,
          },
        ],
        nested_assistants: [],
        creator: 'user-1',
        shared: false,
        is_react: false,
        is_global: false,
      } as unknown as AssistantResponse;

      const result = prepareAssistantForYaml(assistant, state, new Map(), new Map());

      expect(result.mcp_servers).toHaveLength(1);
      const mcp = result.mcp_servers?.[0] as unknown as Record<string, unknown>;
      expect(mcp).not.toHaveProperty('config');
      expect(mcp).not.toHaveProperty('mcp_connect_url');
      expect(mcp).not.toHaveProperty('tools_tokens_size_limit');
      expect(mcp).not.toHaveProperty('mcp_connect_auth_token');
      expect(mcp).toMatchObject({ name: 'Figma MCP', command: 'npx' });
    });
  });

  describe('transformToolkits', () => {
    it('should transform multiple toolkits with tools', () => {
      const integrationMap = new Map<string, string>([
        ['int-jira', 'Jira Connection'],
        ['int-gitlab', 'GitLab Connection'],
      ]);

      const toolkits: ToolKitDetails[] = [
        {
          toolkit: 'jira',
          label: 'Jira Toolkit',
          settings_config: false,
          is_external: false,
          tools: [
            {
              name: 'jira_get_issue',
              label: 'Get Issue',
              settings_config: false,
              settings: {
                id: 'int-jira',
                project_name: 'test-project',
                alias: 'Jira Connection',
                credential_type: 'Jira',
                credential_values: [],
                setting_type: 'project',
              },
            },
          ],
        },
        {
          toolkit: 'gitlab',
          label: 'GitLab Toolkit',
          settings_config: true,
          is_external: false,
          tools: [
            {
              name: 'gitlab_get_file',
              settings_config: false,
              settings: {
                id: 'int-gitlab',
                project_name: 'test-project',
                credential_type: 'Git',
                credential_values: [],
                setting_type: 'project',
              },
            },
          ],
        },
      ];

      const result = transformToolkits(toolkits, integrationMap);

      expect(result).toHaveLength(2);
      expect(result?.[0].toolkit).toBe('jira');
      expect(result?.[0].tools[0].settings).toEqual({ $ref: 'imported.integrations.Jira Connection' });
      expect(result?.[1].toolkit).toBe('gitlab');
      expect(result?.[1].tools[0].settings).toEqual({ $ref: 'imported.integrations.GitLab Connection' });
    });

    it('should handle undefined toolkits', () => {
      const integrationMap = new Map<string, string>();
      const result = transformToolkits(undefined, integrationMap);

      expect(result).toBeUndefined();
    });

    it('should handle empty toolkits array', () => {
      const integrationMap = new Map<string, string>();
      const result = transformToolkits([], integrationMap);

      expect(result).toEqual([]);
    });

    it('should preserve toolkit settings', () => {
      const integrationMap = new Map<string, string>();
      const toolkits: ToolKitDetails[] = [
        {
          toolkit: 'custom',
          label: 'Custom Toolkit',
          settings_config: false,
          is_external: true,
          settings: {
            id: 'int-custom',
            project_name: 'test-project',
            credential_type: 'OpenAPI',
            credential_values: [],
            setting_type: 'project',
          },
          tools: [{ name: 'tool1', settings_config: false }],
        },
      ];

      const result = transformToolkits(toolkits, integrationMap);

      expect(result?.[0].settings).toBeDefined();
      expect(result?.[0].is_external).toBe(true);
    });

    it('should transform all tools in each toolkit', () => {
      const integrationMap = new Map<string, string>([['int-1', 'Integration 1']]);
      const toolkits: ToolKitDetails[] = [
        {
          toolkit: 'multi_tool',
          label: 'Multi Tool Kit',
          settings_config: false,
          is_external: false,
          tools: [
            {
              name: 'tool1',
              settings_config: false,
              settings: {
                id: 'int-1',
                project_name: 'test-project',
                credential_type: 'OpenAPI',
                credential_values: [],
                setting_type: 'project',
              },
            },
            {
              name: 'tool2',
              settings_config: false,
              settings: {
                id: 'int-1',
                project_name: 'test-project',
                credential_type: 'OpenAPI',
                credential_values: [],
                setting_type: 'project',
              },
            },
          ],
        },
      ];

      const result = transformToolkits(toolkits, integrationMap);

      expect(result?.[0].tools).toHaveLength(2);
      expect(result?.[0].tools[0].settings).toEqual({ $ref: 'imported.integrations.Integration 1' });
      expect(result?.[0].tools[1].settings).toEqual({ $ref: 'imported.integrations.Integration 1' });
    });

    it('should extract OpenAPI spec from toolkit-level settings and replace with file reference', () => {
      const integrationMap = new Map<string, string>();
      const integrationSpecPaths = new Map<string, string>([['int-coda-456', 'openapi_specs/coda-api.json']]);

      const largeOpenApiSpec = JSON.stringify({
        openapi: '3.0.0',
        info: { title: 'Coda API', version: '1.0.0' },
        paths: { '/docs': { get: { summary: 'Get docs' } } },
      });

      const toolkits: ToolKitDetails[] = [
        {
          toolkit: 'OpenAPI',
          label: 'Coda Toolkit',
          settings_config: false,
          is_external: false,
          settings: {
            id: 'int-coda-456',
            project_name: 'test-project',
            credential_type: 'OpenAPI',
            credential_values: [
              { key: 'url', value: 'https://coda.io/api' },
              { key: 'openapi_spec', value: largeOpenApiSpec },
            ],
            setting_type: 'project',
          },
          tools: [{ name: 'open_api', settings_config: false, label: 'Invoke API' }],
        },
      ];

      const result = transformToolkits(toolkits, integrationMap, integrationSpecPaths);

      expect(result?.[0].settings).toBeDefined();
      const settings = result?.[0].settings as { credential_values?: Array<{ key: string; value: unknown }> };
      expect(settings.credential_values).toBeDefined();

      const openapiSpecValue = settings.credential_values?.find((cv) => cv.key === 'openapi_spec');
      expect(openapiSpecValue?.value).toBe('openapi_specs/coda-api.json');

      const urlValue = settings.credential_values?.find((cv) => cv.key === 'url');
      expect(urlValue?.value).toBe('https://coda.io/api');
    });
  });

  describe('skill backup partitioning', () => {
    const ownedSkill = createMockSkill({
      id: 'owned-1',
      name: 'owned-skill',
      project: 'test-project',
    });
    const referencedExternalSkill = createMockSkill({
      id: 'external-1',
      name: 'external-skill',
      project: 'epm-cdme',
    });
    const unreferencedExternalSkill = createMockSkill({
      id: 'external-2',
      name: 'unused-external',
      project: 'other-project',
    });

    it('should detect project-owned skills', () => {
      expect(isProjectOwnedSkill(ownedSkill, 'test-project')).toBe(true);
      expect(isProjectOwnedSkill(referencedExternalSkill, 'test-project')).toBe(false);
    });

    it('should collect skill IDs referenced by assistants', () => {
      const assistants: AssistantResponse[] = [
        createMockAssistant({ skill_ids: ['external-1', 'missing-id'] }),
        createMockAssistant({ skill_ids: ['external-1'] }),
      ];

      expect([...collectReferencedSkillIds(assistants)]).toEqual(['external-1', 'missing-id']);
    });

    it('should partition owned and referenced external skills', () => {
      const referencedSkillIds = collectReferencedSkillIds([createMockAssistant({ skill_ids: ['external-1'] })]);

      const result = partitionSkillsForBackupYaml(
        [ownedSkill, referencedExternalSkill, unreferencedExternalSkill],
        'test-project',
        referencedSkillIds
      );

      expect(result.ownedSkills).toEqual([ownedSkill]);
      expect(result.importedSkills).toEqual([referencedExternalSkill]);
      expect(prepareImportedSkillForYaml(referencedExternalSkill)).toEqual({
        name: 'external-skill',
        id: 'external-1',
      });
    });

    it('should write owned skill state when preparing skill resource', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const resource = prepareSkillForYaml(
        createMockSkill({
          id: 'owned-1',
          name: 'owned-skill',
          project: 'test-project',
          description: 'Owned',
          content: '# Owned',
        }),
        state
      );

      expect(resource.name).toBe('owned-skill');
      expect(resource.file).toBe('skills/owned-skill.skill.md');
      expect(state.resources.skills?.['owned-skill']?.id).toBe('owned-1');
    });

    it('round-trips a content-only skill response into a file-based resource with a matching checksum', () => {
      // A SkillResponse from the API always carries its body in `.content` (never a `file`
      // reference); prepareSkillForYaml converts it to a file-based SkillResource (the actual
      // body is written to that file elsewhere, outside this function) and must checksum the
      // response's inline content, not a file it never reads.
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const skillResponse = createMockSkill({
        id: 'inline-1',
        name: 'inline-skill',
        project: 'test-project',
        description: 'Inline',
        content: 'inline body, never backed by a file on disk before this call',
      });

      const resource = prepareSkillForYaml(skillResponse, state);

      expect(resource).toEqual({ name: 'inline-skill', description: 'Inline', file: 'skills/inline-skill.skill.md' });
      expect(resource.content).toBeUndefined();
      expect(state.resources.skills?.['inline-skill']).toMatchObject({
        id: 'inline-1',
        contentChecksum: calculateChecksum(skillResponse.content),
      });
    });

    it('points file at skills/<name>/SKILL.md when the skill response carries companion files', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const skillResponse = createMockSkill({
        id: 'companioned-1',
        name: 'companioned-skill',
        project: 'test-project',
        description: 'Has companions',
        content: '# Companioned Skill',
        companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 12 }],
      });

      const resource = prepareSkillForYaml(skillResponse, state);

      expect(resource.file).toBe('skills/companioned-skill/SKILL.md');
    });

    it('records the companion files checksum of the files backup just wrote to disk', () => {
      const backupDir = fs.mkdtempSync(path.join(os.tmpdir(), 'backup-transformers-test-'));

      try {
        const skillDir = path.join(backupDir, 'skills', 'companioned-skill');
        fs.mkdirSync(skillDir, { recursive: true });
        fs.writeFileSync(path.join(skillDir, 'SKILL.md'), '# Companioned Skill');
        fs.writeFileSync(path.join(skillDir, 'reference.md'), 'reference body');

        const state: StateFile = {
          version: '1.0',
          project: 'test-project',
          lastSync: null,
          resources: {
            assistants: {},
            datasources: {},
            workflows: {},
            skills: {},
          },
        };

        const skillResponse = createMockSkill({
          id: 'companioned-1',
          name: 'companioned-skill',
          project: 'test-project',
          description: 'Has companions',
          content: '# Companioned Skill',
          companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 14 }],
        });

        prepareSkillForYaml(skillResponse, state, backupDir);

        // The same pair deploy/preview recompute from the restored working tree, so the first
        // deploy after a restore must see no companion-file change.
        const expected = calculateCompanionFilesChecksum(collectCompanionFiles(skillDir));
        expect(state.resources.skills?.['companioned-skill']?.companionFilesChecksum).toBe(
          expected.companionFilesChecksum
        );
        expect(state.resources.skills?.['companioned-skill']?.companionFileHashes).toEqual(
          expected.companionFileHashes
        );
      } finally {
        fs.rmSync(backupDir, { recursive: true, force: true });
      }
    });

    it('points a punctuated skill name at the sanitized path the backup writer actually wrote', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      const flat = prepareSkillForYaml(
        createMockSkill({
          id: 'punct-1',
          name: 'Code_Review',
          project: 'test-project',
          description: 'Underscore name',
          content: '# Code Review',
        }),
        state
      );

      expect(flat.file).toBe('skills/code-review.skill.md');

      const companioned = prepareSkillForYaml(
        createMockSkill({
          id: 'punct-2',
          name: 'C++ Helper',
          project: 'test-project',
          description: 'Punctuated name',
          content: '# C++ Helper',
          companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 3 }],
        }),
        state
      );

      expect(companioned.file).toBe('skills/c-helper/SKILL.md');
    });

    it('produces a companion checksum for a punctuated name instead of silently skipping it', () => {
      const backupDir = fs.mkdtempSync(path.join(os.tmpdir(), 'backup-transformers-punct-'));

      try {
        // Exactly what backup.ts writes to disk for this skill name.
        const skillDir = path.join(backupDir, 'skills', 'c-helper');
        fs.mkdirSync(skillDir, { recursive: true });
        fs.writeFileSync(path.join(skillDir, 'SKILL.md'), '# C++ Helper');
        fs.writeFileSync(path.join(skillDir, 'reference.md'), 'reference body');

        const state: StateFile = {
          version: '1.0',
          project: 'test-project',
          lastSync: null,
          resources: {
            assistants: {},
            datasources: {},
            workflows: {},
            skills: {},
          },
        };

        prepareSkillForYaml(
          createMockSkill({
            id: 'punct-3',
            name: 'C++ Helper',
            project: 'test-project',
            description: 'Punctuated name',
            content: '# C++ Helper',
            companion_files: [{ path: 'reference.md', mime_type: 'text/markdown', encoding: 'text', size_bytes: 14 }],
          }),
          state,
          backupDir
        );

        const expected = calculateCompanionFilesChecksum(collectCompanionFiles(skillDir));
        expect(state.resources.skills?.['C++ Helper']?.companionFilesChecksum).toBe(expected.companionFilesChecksum);
        expect(state.resources.skills?.['C++ Helper']?.companionFileHashes).toEqual(expected.companionFileHashes);
      } finally {
        fs.rmSync(backupDir, { recursive: true, force: true });
      }
    });

    it('leaves both companion state fields absent for a skill without companion files', () => {
      const state: StateFile = {
        version: '1.0',
        project: 'test-project',
        lastSync: null,
        resources: {
          assistants: {},
          datasources: {},
          workflows: {},
          skills: {},
        },
      };

      prepareSkillForYaml(
        createMockSkill({
          id: 'plain-1',
          name: 'plain-skill',
          project: 'test-project',
          description: 'No companions',
          content: '# Plain',
        }),
        state,
        os.tmpdir()
      );

      expect(state.resources.skills?.['plain-skill']).not.toHaveProperty('companionFilesChecksum');
      expect(state.resources.skills?.['plain-skill']).not.toHaveProperty('companionFileHashes');
    });
  });
});
