/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import type { Assistant, DataSource, Workflow } from 'codemie-sdk';

import {
  assistantResponseToResource,
  datasourceResponseToResource,
  workflowResponseToResource,
  datasourceResourceToCreateParams,
  assistantResourceToCreateParams,
  skillResponseToResource,
} from './converters';
import { skillFlatFileRelativePath } from './fileUtils';
import { logger } from './logger';

describe('converters', () => {
  describe('assistantResponseToResource', () => {
    describe('deselected_default_tools', () => {
      const base = {
        id: 'ast-1',
        name: 'A',
        description: 'd',
        llm_model_type: 'gpt-4',
        system_prompt: 'p',
        slug: 'a',
      };

      it('includes the list when non-empty', () => {
        const result = assistantResponseToResource({
          ...base,
          deselected_default_tools: ['search_kb'],
        } as unknown as Assistant);
        expect(result).toHaveProperty('deselected_default_tools', ['search_kb']);
      });

      it.each([[[]], [undefined], [null]])('omits the key for %p', (value) => {
        const result = assistantResponseToResource({
          ...base,
          deselected_default_tools: value,
        } as unknown as Assistant);
        expect(result).not.toHaveProperty('deselected_default_tools');
      });
    });

    it('should convert basic assistant', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test Assistant',
        description: 'Test description',
        llm_model_type: 'gpt-4',
        system_prompt: 'You are helpful',
        slug: 'test-assistant',
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result).toEqual({
        name: 'Test Assistant',
        description: 'Test description',
        prompt: 'system_prompts/test-assistant.prompt.md',
        model: 'gpt-4',
      });
    });

    it('should default model to gpt-4', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: undefined as unknown as string,
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.model).toBe('gpt-4');
    });

    it('should use name for prompt filename when slug is missing', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'My Test Assistant',
        llm_model_type: 'gpt-4',
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.prompt).toBe('system_prompts/my-test-assistant.prompt.md');
    });

    it('should include optional fields when present', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        temperature: 0.7,
        top_p: 0.9,
        shared: true,
        is_react: false,
        is_global: true,
        icon_url: 'https://example.com/icon.png',
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result).toMatchObject({
        temperature: 0.7,
        top_p: 0.9,
        shared: true,
        is_react: false,
        is_global: true,
        icon_url: 'https://example.com/icon.png',
      });
    });

    it('should include conversation_starters when present', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        conversation_starters: ['Hello', 'Help'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.conversation_starters).toEqual(['Hello', 'Help']);
    });

    it('should filter invalid MCP servers', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          { name: '', alias: 'test', command: 'cmd', args: [] }, // Invalid: empty name
          { name: 'valid', alias: 'test', command: 'cmd', args: ['arg1'] }, // Valid
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('valid');
    });

    it('should not include mcp_servers when all are invalid', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [{ name: '', alias: 'test', command: '', args: [] }] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should filter MCP server with empty command', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          { name: 'test', alias: 'alias', command: '', args: [] }, // Invalid: empty command
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should filter MCP server with invalid description type', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          { name: 'test', alias: 'alias', command: 'cmd', args: [], description: 123 }, // Invalid: description not string
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should filter MCP server with invalid enabled type', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          { name: 'test', alias: 'alias', command: 'cmd', args: [], enabled: 'yes' }, // Invalid: enabled not boolean
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should accept MCP server with config.command structure (API format)', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'supabase-mcp',
            description: 'Supabase MCP Server',
            enabled: true,
            config: {
              command: 'npx',
              args: ['-y', '@supabase/mcp-server-supabase@latest'],
            },
            command: null,
            arguments: null,
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('supabase-mcp');
      expect(result.mcp_servers?.[0].config).toMatchObject({
        command: 'npx',
        args: ['-y', '@supabase/mcp-server-supabase@latest'],
      });
    });

    it('should accept MCP server with config.url structure (remote MCP)', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'Playwright MCP Server',
            description: 'Remote Playwright',
            enabled: true,
            config: {
              url: 'https://example.com/api/mcp/playwright/',
              args: [],
              headers: { 'X-Api-Key': '$API_KEY' },
              type: 'streamable-http',
            },
            mcp_connect_url: '',
            command: null,
            arguments: null,
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('Playwright MCP Server');
      expect(result.mcp_servers?.[0].config).toMatchObject({
        url: 'https://example.com/api/mcp/playwright/',
        type: 'streamable-http',
      });
      // Null-valued and empty-URL keys are sanitized away before they reach YAML
      expect(result.mcp_servers?.[0]).not.toHaveProperty('mcp_connect_url');
      expect(result.mcp_servers?.[0]).not.toHaveProperty('command');
      expect(result.mcp_servers?.[0]).not.toHaveProperty('arguments');
    });

    it('should preserve MCP server identified only by mcp_config_id', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'RI-logs',
            description: 'Download, unzip and grep log files',
            enabled: true,
            mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
            integration_alias: 'ri-logs-alias',
            resolve_dynamic_values_in_arguments: false,
            tools: ['fetch_logs'],
          },
        ],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0]).toMatchObject({
        name: 'RI-logs',
        description: 'Download, unzip and grep log files',
        enabled: true,
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
        integration_alias: 'ri-logs-alias',
        resolve_dynamic_values_in_arguments: false,
        tools: ['fetch_logs'],
      });
    });

    it('should reject MCP server with both command and url', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'invalid-mcp',
            config: {
              command: 'npx',
              url: 'https://example.com/mcp',
              args: [],
            },
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should accept real API format: legacy with command and arguments string', () => {
      // Real example from backup: "MCP for Atlassian"
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'MCP for Atlassian',
            description: 'Connection to Jira/Confluence',
            enabled: false,
            command: 'uvx',
            arguments: "mcp-atlassian --jira-url 'https://jira.example.com' --jira-username 'user@example.com'",
            config: null,
            mcp_connect_url: '',
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeDefined();
      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('MCP for Atlassian');
      expect(result.mcp_servers?.[0]).not.toHaveProperty('config');
      expect(result.mcp_servers?.[0]).not.toHaveProperty('mcp_connect_url');
      // enabled: false is a real value and must survive sanitization
      expect(result.mcp_servers?.[0].enabled).toBe(false);
    });

    it('should accept real API format: config with command and args array', () => {
      // Real example from backup: "supabase-mcp"
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'supabase-mcp',
            description: 'MCP Server for Supabase',
            enabled: true,
            config: {
              command: 'npx',
              url: null,
              args: ['-y', '@supabase/mcp-server-supabase@latest', '--project-ref=xyz'],
              headers: {},
              env: {},
            },
            command: null,
            arguments: null,
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeDefined();
      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('supabase-mcp');
      expect(result.mcp_servers?.[0].config?.args).toEqual([
        '-y',
        '@supabase/mcp-server-supabase@latest',
        '--project-ref=xyz',
      ]);
    });

    it('should accept real API format: config with url for remote MCP', () => {
      // Real example from backup: "Playwright MCP Server"
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'Playwright MCP Server',
            description: 'Playwright MCP Server',
            enabled: true,
            config: {
              command: null,
              url: 'https://staging.example.io/api/mcp/playwright/',
              args: [],
              headers: { 'X-Api-Key': '$API_KEY' },
              env: {},
              type: 'streamable-http',
            },
            command: null,
            arguments: null,
            tools_tokens_size_limit: 100_000,
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeDefined();
      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('Playwright MCP Server');
      // Note: config structure preserved as-is from API (includes url field)
    });

    it('should accept real API format: Figma with empty mcp_connect_url', () => {
      // Real example from backup: TAD UXD Assistant - Figma MCP
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'TAD UXD Assistant',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'Figma',
            description: 'Figma MCP',
            enabled: true,
            config: null,
            mcp_connect_url: '', // Empty string (not null)
            command: 'npx',
            arguments: '-y figma-developer-mcp --stdio',
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeDefined();
      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('Figma');
      // The empty mcp_connect_url and the null config carry no information
      expect(result.mcp_servers?.[0]).not.toHaveProperty('mcp_connect_url');
      expect(result.mcp_servers?.[0]).not.toHaveProperty('config');
      // Real values survive
      expect(result.mcp_servers?.[0].command).toBe('npx');
      expect(result.mcp_servers?.[0].description).toBe('Figma MCP');
    });

    it('should reject MCP server with neither command nor url', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'invalid-mcp',
            config: {
              command: null,
              url: null,
              args: [],
            },
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toBeUndefined();
    });

    it('should accept MCP server with legacy flat command structure', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test',
        llm_model_type: 'gpt-4',
        mcp_servers: [
          {
            name: 'MCP for Atlassian',
            command: 'uvx',
            arguments: 'mcp-atlassian --jira-url https://jira.com',
            enabled: true,
          },
        ] as unknown as Assistant['mcp_servers'],
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.mcp_servers).toHaveLength(1);
      expect(result.mcp_servers?.[0].name).toBe('MCP for Atlassian');
    });

    it('should convert nested_assistants to sub_assistants', () => {
      const assistant = {
        id: 'ast-123',
        name: 'Parent Assistant',
        llm_model_type: 'gpt-4',
        nested_assistants: [
          { name: 'Helper Assistant 1', id: 'ast-456' },
          { name: 'Helper Assistant 2', id: 'ast-789' },
        ],
      } as unknown as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.sub_assistants).toEqual(['Helper Assistant 1', 'Helper Assistant 2']);
    });

    it('should not include sub_assistants when nested_assistants is missing', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test Assistant',
        llm_model_type: 'gpt-4',
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.sub_assistants).toBeUndefined();
    });

    it('should include prompt_variables when present', () => {
      const assistant = {
        id: 'ast-123',
        name: 'Test Assistant',
        llm_model_type: 'gpt-4',
        prompt_variables: [
          { key: 'api_key', description: 'API Key', default_value: 'default' },
          { key: 'region', default_value: 'us-east-1' },
        ],
      } as unknown as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.prompt_variables).toEqual([
        { key: 'api_key', description: 'API Key', default_value: 'default' },
        { key: 'region', default_value: 'us-east-1' },
      ]);
    });

    it('should include prompt_variables when empty', () => {
      const assistant = {
        id: 'ast-123',
        name: 'Test Assistant',
        llm_model_type: 'gpt-4',
        prompt_variables: [],
      } as unknown as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.prompt_variables).toEqual([]);
    });

    it('should not include prompt_variables when missing', () => {
      const assistant: Assistant = {
        id: 'ast-123',
        name: 'Test Assistant',
        llm_model_type: 'gpt-4',
      } as Assistant;

      const result = assistantResponseToResource(assistant);

      expect(result.prompt_variables).toBeUndefined();
    });
  });

  describe('datasourceResponseToResource', () => {
    it('should convert code datasource with link', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test Repo',
        type: 'code',
        description: 'Test description',
        embeddings_model: 'ada-002',
        setting_id: 'setting-123',
        code: {
          link: 'https://github.com/test/repo',
          branch: 'main',
        },
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Test Repo',
        type: 'code',
        description: 'Test description',
        link: 'https://github.com/test/repo',
        branch: 'main',
      });
    });

    it('should not extract URL from description when code.link is missing (SDK limitation)', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test Repo',
        type: 'code',
        description: 'https://github.com/test/repo Some description',
        embeddings_model: 'ada-002',
        setting_id: 'setting-123',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        type: 'code',
        link: undefined,
        description: 'https://github.com/test/repo Some description',
      });
    });

    it('should not extract git@ URL from description (SDK limitation)', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test Repo',
        type: 'code',
        description: 'Repository: git@github.com:user/repo.git with some notes',
        embeddings_model: 'ada-002',
        setting_id: 'setting-123',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        type: 'code',
        link: undefined,
        description: 'Repository: git@github.com:user/repo.git with some notes',
      });
    });

    it('should not extract ssh:// URL from description (SDK limitation)', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test Repo',
        type: 'code',
        description: 'ssh://git@example.com:7999/project/repo.git is the source',
        embeddings_model: 'ada-002',
        setting_id: 'setting-123',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        type: 'code',
        link: undefined,
        description: 'ssh://git@example.com:7999/project/repo.git is the source',
      });
    });

    it('should handle code datasource without link (SDK limitation)', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test Repo',
        type: 'code',
        description: 'No URL here',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        type: 'code',
        link: undefined,
        description: 'No URL here',
      });
    });

    it('should convert confluence datasource', () => {
      const datasource = {
        id: 'ds-123',
        name: 'Confluence DS',
        type: 'knowledge_base_confluence',
        description: 'Confluence datasource',
        confluence: {
          space_keys: ['PROJ'],
          cql: 'space=PROJ',
        },
      } as unknown as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Confluence DS',
        type: 'knowledge_base_confluence',
        space_keys: ['PROJ'],
        cql: 'space=PROJ',
      });
    });

    it('should convert jira datasource', () => {
      const datasource = {
        id: 'ds-123',
        name: 'Jira DS',
        type: 'knowledge_base_jira',
        jira: {
          project_keys: ['PROJ'],
          jql: 'project=PROJ',
        },
      } as unknown as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Jira DS',
        type: 'knowledge_base_jira',
        project_keys: ['PROJ'],
        jql: 'project=PROJ',
      });
    });

    it('should convert google docs datasource', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Google Doc',
        type: 'llm_routing_google',
        google_doc_link: 'doc-id-123',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Google Doc',
        type: 'llm_routing_google',
        google_doc: 'doc-id-123',
      });
    });

    it('should convert file datasource', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'File DS',
        type: 'knowledge_base_file',
        description: 'Uploaded files',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'File DS',
        type: 'knowledge_base_file',
        description: 'Uploaded files',
      });
    });

    it('should convert bedrock datasource with minimal fields', () => {
      const datasource = {
        id: 'ds-bedrock',
        name: 'Bedrock DS',
        type: 'knowledge_base_bedrock',
        description: 'Bedrock datasource',
        setting_id: 'setting-bedrock',
        shared_with_project: true,
      } as unknown as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Bedrock DS',
        type: 'knowledge_base_bedrock',
        description: 'Bedrock datasource',
        setting_id: 'setting-bedrock',
      });
    });

    it('should convert chunk-summary datasource alias', () => {
      const datasource = {
        id: 'ds-chunk',
        name: 'Chunk Summary DS',
        type: 'chunk-summary',
        description: 'Chunk summary datasource',
      } as unknown as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'Chunk Summary DS',
        type: 'code',
        index_type: 'chunk-summary',
        description: 'Chunk summary datasource',
      });
    });

    it('should convert file-summay datasource alias', () => {
      const datasource = {
        id: 'ds-file-summary',
        name: 'File Summary DS',
        type: 'file-summay',
        description: 'File summary datasource',
      } as unknown as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result).toMatchObject({
        name: 'File Summary DS',
        type: 'code',
        index_type: 'summary',
        description: 'File summary datasource',
      });
    });

    it('should use integration alias for setting_id', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test',
        type: 'code',
        code: { link: 'https://github.com/test/repo' },
      } as DataSource;

      const result = datasourceResponseToResource(datasource, 'my-integration');

      expect(result.setting_id).toBe('$ref:imported.integrations.my-integration.id');
    });

    it('should handle shared_with_project field', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Test',
        type: 'code',
        shared_with_project: false,
        code: { link: 'https://github.com/test/repo' },
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result.shared_with_project).toBe(false);
    });

    it('should handle unknown datasource type gracefully', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Unknown DS',
        type: 'unknown_type' as DataSource['type'],
        description: 'Unknown type',
      } as DataSource;

      const result = datasourceResponseToResource(datasource);

      expect(result.name).toBe('Unknown DS');
      expect(result.type).toBe('unknown_type');
    });

    it('should warn when required by datasource type setting id is missing', () => {
      const datasource = {
        id: 'ds-123',
        name: 'Jira DS',
        type: 'knowledge_base_jira',
        jira: {
          project_keys: ['PROJ'],
          jql: 'project=PROJ',
        },
      } as unknown as DataSource;

      const loggerSpy = jest.spyOn(logger, 'warn');
      datasourceResponseToResource(datasource);

      expect(loggerSpy).toHaveBeenCalledWith(
        expect.stringContaining('Datasource "Jira DS" is missing setting_id (integration reference)')
      );
    });

    it('should not warn about missing setting id for allowed datasources', () => {
      const datasource: DataSource = {
        id: 'ds-123',
        name: 'Google Doc',
        type: 'llm_routing_google',
        google_doc_link: 'doc-id-123',
      } as DataSource;

      const loggerSpy = jest.spyOn(logger, 'warn');
      datasourceResponseToResource(datasource);

      expect(loggerSpy).not.toHaveBeenCalled();
    });

    it('should not warn about missing setting id for bedrock datasource', () => {
      const loggerSpy = jest.spyOn(logger, 'warn');

      datasourceResponseToResource({
        id: 'ds-bedrock',
        name: 'Bedrock DS',
        type: 'knowledge_base_bedrock',
      } as unknown as DataSource);

      expect(loggerSpy).not.toHaveBeenCalled();
    });

    it('should warn about missing setting id for code-family summary datasource aliases', () => {
      const loggerSpy = jest.spyOn(logger, 'warn');

      datasourceResponseToResource({
        id: 'ds-chunk',
        name: 'Chunk Summary DS',
        type: 'chunk-summary',
      } as unknown as DataSource);

      datasourceResponseToResource({
        id: 'ds-file-summary',
        name: 'File Summary DS',
        type: 'file-summay',
      } as unknown as DataSource);

      expect(loggerSpy).toHaveBeenCalledWith(
        expect.stringContaining('Datasource "Chunk Summary DS" is missing setting_id')
      );
      expect(loggerSpy).toHaveBeenCalledWith(
        expect.stringContaining('Datasource "File Summary DS" is missing setting_id')
      );
    });
  });

  describe('workflowResponseToResource', () => {
    it('should convert basic workflow', () => {
      const workflow: Workflow = {
        id: 'wf-123',
        name: 'Test Workflow',
        description: 'Test description',
      } as Workflow;

      const result = workflowResponseToResource(workflow);

      expect(result).toEqual({
        name: 'Test Workflow',
        description: 'Test description',
        definition: 'workflows/test-workflow.yaml',
      });
    });

    it('should include optional fields when present', () => {
      const workflow = {
        id: 'wf-123',
        name: 'Test',
        mode: 'Parallel',
        shared: false,
        icon_url: 'https://example.com/icon.png',
      } as unknown as Workflow;

      const result = workflowResponseToResource(workflow);

      expect(result).toMatchObject({
        mode: 'Parallel',
        shared: false,
        icon_url: 'https://example.com/icon.png',
      });
    });

    it('should handle empty description', () => {
      const workflow: Workflow = {
        id: 'wf-123',
        name: 'Test',
        description: undefined,
      } as unknown as Workflow;

      const result = workflowResponseToResource(workflow);

      expect(result.description).toBe('');
    });

    it('should normalize workflow name for filename', () => {
      const workflow: Workflow = {
        id: 'wf-123',
        name: 'My Test Workflow',
      } as Workflow;

      const result = workflowResponseToResource(workflow);

      expect(result.definition).toBe('workflows/my-test-workflow.yaml');
    });
  });

  describe('datasourceResourceToCreateParams', () => {
    it('should convert code datasource', () => {
      const datasource = {
        name: 'Test Repo',
        type: 'code' as const,
        description: 'Test',
        link: 'https://github.com/test/repo',
        branch: 'main',
      };

      const result = datasourceResourceToCreateParams(datasource, 'test-project');

      expect(result).toMatchObject({
        name: 'Test Repo',
        type: 'code',
        link: 'https://github.com/test/repo',
        branch: 'main',
        project_name: 'test-project',
        shared_with_project: true,
      });
    });

    it('should exclude $ref field', () => {
      const datasource = {
        name: 'Test',
        type: 'code' as const,
        description: 'Test',
        link: 'https://github.com/test/repo',
        $ref: 'code',
      };

      const result = datasourceResourceToCreateParams(datasource, 'test-project');

      expect(result).not.toHaveProperty('$ref');
    });

    it('should exclude force_reindex field', () => {
      const datasource = {
        name: 'Test',
        type: 'code' as const,
        description: 'Test',
        link: 'https://github.com/test/repo',
        force_reindex: true,
      };

      const result = datasourceResourceToCreateParams(datasource, 'test-project');

      expect(result).not.toHaveProperty('force_reindex');
    });

    it('should throw error for code datasource without link', () => {
      const datasource = {
        name: 'Test',
        type: 'code' as const,
        description: 'Test',
      };

      expect(() => datasourceResourceToCreateParams(datasource, 'test-project')).toThrow(
        'Invalid code datasource "Test": missing required field "link"'
      );
    });

    it('should throw error for confluence datasource without cql', () => {
      const datasource = {
        name: 'Test',
        type: 'knowledge_base_confluence' as const,
        description: 'Test',
        space_keys: ['PROJ'],
      };

      expect(() => datasourceResourceToCreateParams(datasource, 'test-project')).toThrow(
        'Invalid Confluence datasource "Test": missing required field "cql"'
      );
    });

    it('should throw error for jira datasource without jql', () => {
      const datasource = {
        name: 'Test',
        type: 'knowledge_base_jira' as const,
        description: 'Test',
        project_keys: ['PROJ'],
      };

      expect(() => datasourceResourceToCreateParams(datasource, 'test-project')).toThrow(
        'Invalid Jira datasource "Test": missing required field "jql"'
      );
    });

    it('should throw error for google docs datasource without google_doc', () => {
      const datasource = {
        name: 'Test',
        type: 'llm_routing_google' as const,
        description: 'Test',
      };

      expect(() => datasourceResourceToCreateParams(datasource, 'test-project')).toThrow(
        'Invalid Google Docs datasource "Test": missing required field "google_doc"'
      );
    });

    it('should default shared_with_project to true', () => {
      const datasource = {
        name: 'Test',
        type: 'code' as const,
        description: 'Test',
        link: 'https://github.com/test/repo',
      };

      const result = datasourceResourceToCreateParams(datasource, 'test-project');

      expect(result.shared_with_project).toBe(true);
    });

    it('should respect explicit shared_with_project value', () => {
      const datasource = {
        name: 'Test',
        type: 'code' as const,
        description: 'Test',
        link: 'https://github.com/test/repo',
        shared_with_project: false,
      };

      const result = datasourceResourceToCreateParams(datasource, 'test-project');

      expect(result.shared_with_project).toBe(false);
    });
  });

  describe('assistantResourceToCreateParams', () => {
    describe('deselected_default_tools pass-through', () => {
      const base = { name: 'T', description: 'T', prompt: 'p.md', model: 'gpt-4' };

      it('sends a non-empty list', () => {
        const result = assistantResourceToCreateParams(
          { ...base, deselected_default_tools: ['search_kb', 'search_code_repo'] },
          'proj',
          'x'
        );
        expect(result).toHaveProperty('deselected_default_tools', ['search_kb', 'search_code_repo']);
      });

      it('sends an explicit empty list as []', () => {
        const result = assistantResourceToCreateParams({ ...base, deselected_default_tools: [] }, 'proj', 'x');
        expect(result).toHaveProperty('deselected_default_tools', []);
      });

      it('omits the key when absent (no defaulting)', () => {
        const result = assistantResourceToCreateParams(base, 'proj', 'x');
        expect(result).not.toHaveProperty('deselected_default_tools');
      });
    });

    it('should convert basic assistant', () => {
      const assistant = {
        name: 'Test Assistant',
        description: 'Test description',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result).toMatchObject({
        name: 'Test Assistant',
        description: 'Test description',
        llm_model_type: 'gpt-4',
        system_prompt: 'You are helpful',
        project: 'test-project',
        shared: true,
      });
    });

    it('should exclude IaC-only fields', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        config: 'config.yaml',
        sub_assistants: ['Helper1'],
        datasource_names: ['DS1'],
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result).not.toHaveProperty('prompt');
      expect(result).not.toHaveProperty('config');
      expect(result).not.toHaveProperty('model');
      expect(result).not.toHaveProperty('sub_assistants');
      expect(result).not.toHaveProperty('datasource_names');
    });

    it('should default arrays to empty', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.conversation_starters).toEqual([]);
      expect(result.toolkits).toEqual([]);
      expect(result.context).toEqual([]);
      expect(result.mcp_servers).toEqual([]);
      expect(result.assistant_ids).toEqual([]);
    });

    it('should default shared to true', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.shared).toBe(true);
    });

    it('should respect explicit shared value', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        shared: false,
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.shared).toBe(false);
    });

    it('should round-trip mcp_config_id through create params conversion', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        mcp_servers: [
          {
            name: 'RI-logs',
            enabled: true,
            mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
          },
        ],
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.mcp_servers?.[0]).toMatchObject({
        name: 'RI-logs',
        enabled: true,
        mcp_config_id: 'a6395977-3598-4a0a-bfb3-08463d484575',
      });
    });

    it('should drop null-valued MCP keys from the SDK payload', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        mcp_servers: [
          {
            name: 'Figma',
            command: 'npx',
            arguments: '-y figma-developer-mcp --stdio',
            config: null,
            mcp_connect_url: '',
            tools_tokens_size_limit: null,
          },
        ],
      } as unknown as Parameters<typeof assistantResourceToCreateParams>[0];

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      const mcp = result.mcp_servers?.[0] as unknown as Record<string, unknown>;
      expect(mcp).not.toHaveProperty('config');
      expect(mcp).not.toHaveProperty('mcp_connect_url');
      expect(mcp).not.toHaveProperty('tools_tokens_size_limit');
      expect(mcp.command).toBe('npx');
    });

    it('should default MCP enabled to true when absent in the SDK payload', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        mcp_servers: [{ name: 'RI-logs', mcp_config_id: 'cfg-1' }],
      } as unknown as Parameters<typeof assistantResourceToCreateParams>[0];

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.mcp_servers?.[0].enabled).toBe(true);
      expect(result.mcp_servers?.[0]).toMatchObject({ mcp_config_id: 'cfg-1' });
    });

    it('should keep MCP enabled false in the SDK payload', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        mcp_servers: [{ name: 'RI-logs', mcp_config_id: 'cfg-1', enabled: false }],
      } as unknown as Parameters<typeof assistantResourceToCreateParams>[0];

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result.mcp_servers?.[0].enabled).toBe(false);
    });

    it('should include optional fields when present', () => {
      const assistant = {
        name: 'Test',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
        temperature: 0.7,
        top_p: 0.9,
        conversation_starters: ['Hello'],
      };

      const result = assistantResourceToCreateParams(assistant, 'test-project', 'You are helpful');

      expect(result).toMatchObject({
        temperature: 0.7,
        top_p: 0.9,
        conversation_starters: ['Hello'],
      });
    });
  });
});

describe('skillResponseToResource', () => {
  it('points file at the same sanitized path the backup and import writers use', () => {
    // Backup writes the skill through sanitizeFileName; deriving the YAML path a second way made
    // a punctuated name point at a file that was never written.
    for (const name of ['C++ Helper', 'Code_Review', 'Plain Skill']) {
      const resource = skillResponseToResource({
        id: 'sk-1',
        name,
        description: 'Punctuated name',
        content: '# Body',
      } as Parameters<typeof skillResponseToResource>[0]);

      expect(resource.file).toBe(skillFlatFileRelativePath(name));
    }
  });

  it('keeps a plain name on the existing skills/<name>.skill.md shape', () => {
    const resource = skillResponseToResource({
      id: 'sk-2',
      name: 'My Skill',
      description: 'Plain',
      content: '# Body',
    } as Parameters<typeof skillResponseToResource>[0]);

    expect(resource).toEqual({ name: 'My Skill', description: 'Plain', file: 'skills/my-skill.skill.md' });
  });
});
