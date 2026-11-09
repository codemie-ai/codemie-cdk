/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { AppConfig } from '../appConfig';
import type { CodemieConfig, CodeDatasourceResource } from '../types/codemieConfig';

import { CodemieConfigLoader } from './codemieConfigLoader';

describe('CodemieConfigLoader', () => {
  let tempDir: string;
  let configLoader: CodemieConfigLoader;

  beforeEach(() => {
    // Create temporary directory for each test
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codemie-config-test-'));
    const appConfig: AppConfig = {
      rootDir: tempDir,
      codemieConfig: 'codemie.yaml',
      codemieState: 'state.json',
      backupsDirectory: 'backups',
    };
    configLoader = new CodemieConfigLoader(appConfig);
  });

  afterEach(() => {
    // Clean up temporary directory after each test
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  describe('loadConfig', () => {
    test('should throw error when config file does not exist', () => {
      expect(() => configLoader.loadConfig()).toThrow('Configuration file not found');
    });

    test('should load and parse valid YAML config', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.version).toBe(1);
      expect(loaded.project.name).toBe('test-project');
      expect(loaded.resources).toBeDefined();
    });

    test('should substitute environment variables', () => {
      process.env.TEST_PROJECT_NAME = 'env-project';

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: \${TEST_PROJECT_NAME}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.project.name).toBe('env-project');

      delete process.env.TEST_PROJECT_NAME;
    });

    test('should use default value when env var not set', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: \${MISSING_VAR:default-name}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.project.name).toBe('default-name');
    });

    test('should throw error when required env var not set', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: \${REQUIRED_VAR}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('Environment variable REQUIRED_VAR is not set');
    });

    test('should substitute env vars inside a non-skill resource array element', () => {
      process.env.TEST_DATASOURCE_SUFFIX = 'from-env';

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  datasources:
    - name: repo-\${TEST_DATASOURCE_SUFFIX}
      type: code
    - name: repo-\${MISSING_DATASOURCE_SUFFIX:-from-default}
      type: code
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.resources.datasources?.[0].name).toBe('repo-from-env');
      expect(loaded.resources.datasources?.[1].name).toBe('repo-from-default');

      delete process.env.TEST_DATASOURCE_SUFFIX;
    });

    test('should name the config path when an env var inside an array element is not set', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  datasources:
    - name: repo-\${UNSET_DATASOURCE_SUFFIX}
      type: code
`
      );

      expect(() => configLoader.loadConfig()).toThrow(
        'Environment variable UNSET_DATASOURCE_SUFFIX is not set (referenced in resources.datasources[0].name)'
      );
    });

    test('should use shell-style default syntax with hyphen', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: \${MISSING_VAR:-shell-default}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.project.name).toBe('shell-default');
    });

    test('should return empty string for empty shell-style default when env var not set', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test
environment:
  optional_value: \${OPTIONAL_VAR:-}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect((loaded.environment as Record<string, unknown>).optional_value).toBe('');
    });

    test('should return empty string for empty simple default when env var not set', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test
environment:
  optional_value: \${OPTIONAL_VAR:}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect((loaded.environment as Record<string, unknown>).optional_value).toBe('');
    });

    test('should use env var value even when default is provided', () => {
      process.env.SET_VAR = 'actual-value';

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: \${SET_VAR:-default-value}
resources:
  assistants: []
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.project.name).toBe('actual-value');

      delete process.env.SET_VAR;
    });

    test.each([
      [`$\${CODEMIE_ESCAPE_TEST}`, `\${CODEMIE_ESCAPE_TEST}`],
      [`$\${CODEMIE_ESCAPE_MISSING}`, `\${CODEMIE_ESCAPE_MISSING}`],
      [`$\${CODEMIE_ESCAPE_MISSING:-fallback}`, `\${CODEMIE_ESCAPE_MISSING:-fallback}`],
      [`$\${CODEMIE_ESCAPE_MISSING:fallback}`, `\${CODEMIE_ESCAPE_MISSING:fallback}`],
      [`$\${CODEMIE_ESCAPE_MISSING:-}`, `\${CODEMIE_ESCAPE_MISSING:-}`],
      [`$\${CODEMIE_ESCAPE_MISSING:}`, `\${CODEMIE_ESCAPE_MISSING:}`],
      [`$\${CODEMIE_ESCAPE_TEST} / \${CODEMIE_ESCAPE_TEST}`, `\${CODEMIE_ESCAPE_TEST} / local-value`],
      [`$\${CODEMIE_ESCAPE_TEST}$\${CODEMIE_ESCAPE_MISSING}`, `\${CODEMIE_ESCAPE_TEST}\${CODEMIE_ESCAPE_MISSING}`],
      [`prefix-$\${CODEMIE_ESCAPE_TEST}-suffix`, `prefix-\${CODEMIE_ESCAPE_TEST}-suffix`],
      [`$$\${CODEMIE_ESCAPE_TEST}`, `$\${CODEMIE_ESCAPE_TEST}`],
      ['plain $ and $$ and $NAME', 'plain $ and $$ and $NAME'],
    ])('should load literal placeholders in %s without expanding them again', (input, expected) => {
      const env: NodeJS.ProcessEnv = { ...process.env, CODEMIE_ESCAPE_TEST: 'local-value' };
      delete env.CODEMIE_ESCAPE_MISSING;
      jest.replaceProperty(process, 'env', env);
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        JSON.stringify({ version: '1', project: { name: input }, resources: {} })
      );

      expect(configLoader.loadConfig().project.name).toBe(expected);
    });

    test('should preserve escaped MCP placeholders in imported arrays alongside normal substitutions', () => {
      const env: NodeJS.ProcessEnv = { ...process.env, CODEMIE_ESCAPE_TEST: 'local-value' };
      delete env.CODEMIE_ESCAPE_MISSING;
      jest.replaceProperty(process, 'env', env);
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        JSON.stringify({
          version: '1',
          project: { name: 'test-project' },
          resources: { assistants: [{ $import: 'assistant.yaml' }] },
        })
      );
      fs.writeFileSync(
        path.join(tempDir, 'assistant.yaml'),
        JSON.stringify({
          name: 'example-assistant',
          mcp_servers: [
            {
              name: 'example-mcp',
              enabled: true,
              config: {
                env: { TOKEN: `$\${CODEMIE_ESCAPE_MISSING}`, LOCAL: `\${CODEMIE_ESCAPE_TEST}` },
                args: [`$\${CODEMIE_ESCAPE_TEST}`, `\${CODEMIE_ESCAPE_TEST}`],
              },
            },
          ],
        })
      );

      const mcp = configLoader.loadConfig().resources.assistants?.[0].mcp_servers?.[0];
      expect(mcp?.config?.env).toEqual({ TOKEN: `\${CODEMIE_ESCAPE_MISSING}`, LOCAL: 'local-value' });
      expect(mcp?.config?.args).toEqual([`\${CODEMIE_ESCAPE_TEST}`, 'local-value']);
    });

    test('should not expand placeholders introduced by environment values', () => {
      jest.replaceProperty(process, 'env', { ...process.env, CODEMIE_ESCAPE_TEST: `\${CODEMIE_ESCAPE_MISSING}` });
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        JSON.stringify({ version: '1', project: { name: `\${CODEMIE_ESCAPE_TEST}` }, resources: {} })
      );

      expect(configLoader.loadConfig().project.name).toBe(`\${CODEMIE_ESCAPE_MISSING}`);
    });

    test('should apply datasource defaults by type', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
datasource_defaults:
  code:
    embeddings_model: ada-002
    branch: master
resources:
  datasources:
    - name: My Repo
      type: code
      link: https://example.com
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      const ds = loaded.resources.datasources![0] as CodeDatasourceResource;
      expect(ds.type).toBe('code');
      expect(ds.embeddings_model).toBe('ada-002');
      expect(ds.branch).toBe('master');
      expect(ds.link).toBe('https://example.com');
    });

    test('should apply datasource defaults via $ref', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
datasource_defaults:
  my_template:
    type: code
    embeddings_model: custom-model
    branch: main
resources:
  datasources:
    - name: My Repo
      $ref: datasource_defaults.my_template
      link: https://example.com
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      const ds = loaded.resources.datasources![0] as CodeDatasourceResource;
      expect(ds.type).toBe('code');
      expect(ds.embeddings_model).toBe('custom-model');
      expect(ds.branch).toBe('main');
      expect(ds.link).toBe('https://example.com');
      expect(ds.$ref).toBeUndefined(); // $ref should be removed
    });

    test('should override defaults with datasource-specific values', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
datasource_defaults:
  code:
    embeddings_model: ada-002
    branch: master
resources:
  datasources:
    - name: My Repo
      type: code
      link: https://example.com
      branch: develop
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      const ds = loaded.resources.datasources![0] as CodeDatasourceResource;
      expect(ds.embeddings_model).toBe('ada-002'); // From defaults
      expect(ds.branch).toBe('develop'); // Overridden
    });

    test('should resolve integration references in datasources', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: git_conn
      id: integration-uuid-123
      credential_type: Git
resources:
  datasources:
    - name: My Repo
      type: code
      link: https://example.com
      setting_id: $ref:imported.integrations.git_conn.id
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.resources.datasources![0].setting_id).toBe('integration-uuid-123');
    });

    test('should throw error when datasource integration ref does not point to string', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: git_conn
      id: integration-uuid-123
      type: git
resources:
  datasources:
    - name: My Repo
      type: code
      setting_id: $ref:imported.integrations.git_conn
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('must point to a string UUID value');
    });
  });

  describe('loadConfig skill source_dir expansion', () => {
    function writeSkillMd(sourceDirName: string, skillDirName: string, name: string, description: string): void {
      const dirPath = path.join(tempDir, sourceDirName, skillDirName);
      fs.mkdirSync(dirPath, { recursive: true });
      fs.writeFileSync(
        path.join(dirPath, 'SKILL.md'),
        ['---', `name: ${name}`, `description: ${description}`, '---', `Body for ${name}.`].join('\n')
      );
    }

    test('should return flat expanded skill resources from a source_dir entry', () => {
      writeSkillMd('skills-src', 'alpha-skill', 'alpha-skill', 'Alpha skill description text here');

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  skills:
    - name: placeholder
      description: placeholder description long enough
      source_dir: skills-src
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.resources.skills).toHaveLength(1);
      expect(loaded.resources.skills![0]).toMatchObject({
        name: 'alpha-skill',
        description: 'Alpha skill description text here',
        content: 'Body for alpha-skill.',
      });
      expect(loaded.resources.skills![0].source_dir).toBeUndefined();
    });

    test('should substitute an environment variable inside source_dir before expanding', () => {
      process.env.SKILLS_DIR_TEST = 'skills-src';
      writeSkillMd('skills-src', 'env-skill', 'env-skill', 'Env skill description text here');

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  skills:
    - name: placeholder
      description: placeholder description long enough
      source_dir: \${SKILLS_DIR_TEST}
`
      );

      try {
        const loaded = configLoader.loadConfig();

        expect(loaded.resources.skills).toHaveLength(1);
        expect(loaded.resources.skills![0].name).toBe('env-skill');
      } finally {
        delete process.env.SKILLS_DIR_TEST;
      }
    });

    test('should resolve a $ref inside an expanded skill entry after expansion', () => {
      writeSkillMd('skills-src', 'ref-skill', 'ref-skill', 'Ref skill description text here');

      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
shared_values:
  vis: public
resources:
  skills:
    - name: placeholder
      description: placeholder description long enough
      source_dir: skills-src
      visibility: $ref:shared_values.vis
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.resources.skills).toHaveLength(1);
      expect(loaded.resources.skills![0].name).toBe('ref-skill');
      expect(loaded.resources.skills![0].visibility).toBe('public');
    });
  });

  describe('Reference resolution with array search', () => {
    test('should resolve integration reference by alias field', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: jira_main
      id: integration-jira-123
      credential_type: Jira
    - alias: git_conn
      id: integration-git-456
      credential_type: Git
resources:
  datasources:
    - name: My Repo
      type: code
      link: https://example.com
      setting_id: $ref:imported.integrations.git_conn.id
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      expect(loaded.resources.datasources![0].setting_id).toBe('integration-git-456');
    });

    test('should resolve tool reference by name field from tool_definitions', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
tool_definitions:
  - name: create_ticket
    description: Create a ticket
    input_schema:
      type: object
      properties:
        title:
          type: string
  - name: another_tool
    description: Another tool
    input_schema:
      type: object
resources:
  assistants:
    - name: Test Assistant
      model: claude-3-7-sonnet
      system_prompt: test
      toolkits:
        - toolkit: custom_tools
          tools:
            - { "$ref": "tool_definitions.create_ticket" }
  datasources: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();
      const toolkit = loaded.resources.assistants![0].toolkits![0];

      expect(toolkit.tools).toHaveLength(1);
      expect(toolkit.tools[0].name).toBe('create_ticket');
    });

    test('should search in array when referencing nested field after array', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: first_integration
      id: integration-111
      credential_type: Jira
    - alias: second_integration
      id: integration-222
      credential_type: Git
resources:
  datasources:
    - name: Second Integration Repo
      type: code
      link: https://example.com
      setting_id: $ref:imported.integrations.second_integration.id
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      // This verifies that the array search logic correctly finds "second_integration"
      // even though it's not the first item, proving the search works
      expect(loaded.resources.datasources![0].setting_id).toBe('integration-222');
    });

    test('should throw error when integration with specified alias not found', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: jira_main
      id: integration-123
      credential_type: Jira
resources:
  datasources:
    - name: My Repo
      type: code
      link: https://example.com
      setting_id: $ref:imported.integrations.nonexistent_conn.id
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow(
        'no item with alias="nonexistent_conn" in "imported.integrations"'
      );
    });

    test('should throw error when searching for non-existent integration by alias', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: existing_integration
      id: integration-123
      credential_type: Jira
resources:
  datasources:
    - name: My Datasource
      type: code
      link: https://example.com
      setting_id: $ref:imported.integrations.missing_integration.id
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow(
        'no item with alias="missing_integration" in "imported.integrations"'
      );
    });

    test('should throw error when searching for non-existent tool by name', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
tool_definitions:
  - name: existing_tool
    description: test
    input_schema: {}
resources:
  assistants:
    - name: Test Assistant
      model: claude-3-7-sonnet
      system_prompt: test
      toolkits:
        - toolkit: custom
          tools:
            - { "$ref": "tool_definitions.nonexistent_tool" }
  datasources: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('no item with name="nonexistent_tool" in "tool_definitions"');
    });

    test('should handle multiple levels of nesting after array search', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: git_conn
      id: integration-git-456
      credential_type: Git
      metadata:
        nested:
          value: deep_value
resources:
  datasources: []
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      // This test verifies the config loads successfully with nested structure
      // The actual resolution happens when references are used
      expect(loaded.imported?.integrations).toHaveLength(1);
      expect(loaded.imported?.integrations[0].alias).toBe('git_conn');
    });
  });

  describe('loadPrompt', () => {
    test('should load prompt file', () => {
      const promptContent = 'You are a helpful assistant.';
      fs.writeFileSync(path.join(tempDir, 'prompt.md'), promptContent);

      const loaded = configLoader.loadPrompt('prompt.md');

      expect(loaded).toBe(promptContent);
    });

    test('should throw error when prompt file does not exist', () => {
      expect(() => configLoader.loadPrompt('missing.md')).toThrow('Prompt file not found');
    });
  });

  describe('loadAssistantConfig', () => {
    test('should load assistant config file', () => {
      fs.writeFileSync(path.join(tempDir, 'config.yaml'), 'temperature: 0.7\nmax_tokens: 1000\n');

      const loaded = configLoader.loadAssistantConfig('config.yaml');

      expect(loaded).toBeDefined();
      expect(typeof loaded).toBe('object');
    });

    test('should throw error when config file does not exist', () => {
      expect(() => configLoader.loadAssistantConfig('missing.yaml')).toThrow('Config file not found');
    });
  });

  describe('validateFiles', () => {
    test('should pass validation when all files exist', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  assistants:
    - name: Test Assistant
      prompt: ./prompt.md
      model: gpt-4o
      description: Test assistant
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'prompt.md'), 'Test prompt');

      const config = configLoader.loadConfig();
      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    test('should fail validation when prompt file missing', () => {
      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          assistants: [
            {
              name: 'Test Assistant',
              prompt: './missing.md',
              model: 'gpt-4o',
              description: 'Test',
            },
          ],
        },
      } as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.errors[0]).toMatch(/Prompt file not found/);
    });

    test('should report a missing prompt key instead of throwing', () => {
      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          assistants: [
            {
              name: 'Test Assistant',
              // No prompt key at all — the platform returned no system_prompt on import
              model: 'gpt-4o',
              description: 'Test',
            },
          ],
        },
      } as unknown as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Missing 'prompt' for assistant: Test Assistant");
    });

    test('should report an error instead of throwing when a skill has neither file nor content', () => {
      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          skills: [
            {
              name: 'Test Skill',
              // Neither 'file' nor 'content' key at all
              description: 'Test',
            },
          ],
        },
      } as unknown as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Skill 'Test Skill' must specify at least one of 'file' or 'content'");
    });

    test('should accept a skill that declares both file and content', () => {
      fs.writeFileSync(path.join(tempDir, 'skill.md'), 'content');

      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          skills: [
            {
              name: 'Test Skill',
              file: './skill.md',
              content: 'inline content',
              description: 'A perfectly fine description here',
            },
          ],
        },
      } as unknown as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.errors).toEqual([]);
      expect(result.valid).toBe(true);
    });

    test('should validate a source_dir-expanded config without reporting a file/content error', () => {
      const skillDir = path.join(tempDir, 'skills-src', 'my-skill');
      fs.mkdirSync(skillDir, { recursive: true });
      fs.writeFileSync(
        path.join(skillDir, 'SKILL.md'),
        ['---', 'name: my-skill', 'description: A perfectly fine description here', '---', 'Skill body.'].join('\n')
      );
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  skills:
    - source_dir: skills-src
`
      );

      const config = configLoader.loadConfig();
      const result = configLoader.validateFiles(config);

      expect(result.errors).toEqual([]);
      expect(result.valid).toBe(true);
    });

    test('should fail validation when required fields missing', () => {
      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          assistants: [
            {
              name: 'Test Assistant',
              prompt: './prompt.md',
              // Missing model
              // Missing description
            },
          ],
        },
      } as CodemieConfig;

      fs.writeFileSync(path.join(tempDir, 'prompt.md'), 'Test');

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Missing 'model' for assistant: Test Assistant");
      expect(result.errors).toContain("Missing 'description' for assistant: Test Assistant");
    });

    test('should validate optional config file if provided', () => {
      fs.writeFileSync(path.join(tempDir, 'prompt.md'), 'Test');

      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          assistants: [
            {
              name: 'Test Assistant',
              prompt: './prompt.md',
              model: 'gpt-4o',
              description: 'Test',
              config: './missing-config.yaml',
            },
          ],
        },
      } as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors[0]).toMatch(/Config file not found/);
    });

    test('should report skill description out of range via validateSkillDescriptions', () => {
      fs.writeFileSync(path.join(tempDir, 'skill.md'), 'content');

      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        resources: {
          skills: [{ name: 'Test Skill', file: './skill.md', description: 'short' }],
        },
      } as unknown as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        '❌ Skill "Test Skill" description length is 5 characters\n' + '   💡 Allowed range: 10-1000 characters'
      );
      expect(result.errors).not.toContain("Missing 'description' for skill: Test Skill");
    });

    test('should fail validation when imported skill is missing id', () => {
      const config = {
        version: '1',
        project: { name: 'test-project', description: 'Test project' },
        imported: {
          skills: [{ name: 'marketplace-skill' }],
        },
        resources: {},
      } as CodemieConfig;

      const result = configLoader.validateFiles(config);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Imported skill "marketplace-skill" is missing required field: id');
    });
  });

  describe('reference resolution', () => {
    test('should throw error for invalid ref format', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  datasources:
    - name: Test
      type: code
      setting_id: $ref:invalid
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('Invalid $ref format');
    });

    test('should throw error when reference path not found in datasource defaults', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
datasource_defaults:
  existing: 
    type: code
resources:
  datasources:
    - name: Test
      type: code
      $ref: datasource_defaults.non_existent
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('not found');
    });
  });

  describe('context_definitions resolution', () => {
    test('should resolve context reference to array using string format $ref:path', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  frontend_repos:
    - context_type: code
      name: ui-repo
    - context_type: code
      name: components-repo
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.frontend_repos
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(2);
      expect(assistant.context![0]).toEqual({ context_type: 'code', name: 'ui-repo' });
      expect(assistant.context![1]).toEqual({ context_type: 'code', name: 'components-repo' });
    });

    test('should resolve nested $ref in context_definitions arrays', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  frontend_repos:
    - context_type: code
      name: ui-repo
  backend_repos:
    - context_type: code
      name: api-repo
  all_repos:
    - { "$ref": "context_definitions.frontend_repos" }
    - { "$ref": "context_definitions.backend_repos" }
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.all_repos
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(2);
      expect(assistant.context![0]).toEqual({ context_type: 'code', name: 'ui-repo' });
      expect(assistant.context![1]).toEqual({ context_type: 'code', name: 'api-repo' });
    });

    test('should handle mixed inline items and $ref in context_definitions', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  backend_repos:
    - context_type: code
      name: api-repo
  all_repos:
    - { "$ref": "context_definitions.backend_repos" }
    - context_type: code
      name: extra-repo
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.all_repos
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(2);
      expect(assistant.context![0]).toEqual({ context_type: 'code', name: 'api-repo' });
      expect(assistant.context![1]).toEqual({ context_type: 'code', name: 'extra-repo' });
    });

    test('should throw error when context_definitions reference not found (string format)', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  existing_repos:
    - context_type: code
      name: ui-repo
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.nonexistent_repos
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      expect(() => configLoader.loadConfig()).toThrow('not found');
      expect(() => configLoader.loadConfig()).toThrow('context_definitions.nonexistent_repos');
    });

    test('should resolve context using array format with $ref objects', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  knowledge_bases:
    - context_type: knowledge_base
      name: jira-kb
    - context_type: knowledge_base
      name: confluence-kb
  code_repos:
    - context_type: code
      name: repo1
    - context_type: code
      name: repo2
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - { "$ref": "context_definitions.knowledge_bases" }
        - { "$ref": "context_definitions.code_repos" }
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(4);
      expect(assistant.context![0]).toEqual({ context_type: 'knowledge_base', name: 'jira-kb' });
      expect(assistant.context![1]).toEqual({ context_type: 'knowledge_base', name: 'confluence-kb' });
      expect(assistant.context![2]).toEqual({ context_type: 'code', name: 'repo1' });
      expect(assistant.context![3]).toEqual({ context_type: 'code', name: 'repo2' });
    });

    test('should handle array format with $ref YAML shorthand (- $ref: path)', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  frontend:
    - context_type: code
      name: ui-app
  backend:
    - context_type: code
      name: api-server
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - $ref: context_definitions.frontend
        - $ref: context_definitions.backend
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(2);
      expect(assistant.context![0]).toEqual({ context_type: 'code', name: 'ui-app' });
      expect(assistant.context![1]).toEqual({ context_type: 'code', name: 'api-server' });
    });

    test('should throw error when context_definitions reference not found (array format)', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  existing_repos:
    - context_type: code
      name: ui-repo
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - $ref: context_definitions.nonexistent_repos
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      expect(() => configLoader.loadConfig()).toThrow('not found');
      expect(() => configLoader.loadConfig()).toThrow('context_definitions.nonexistent_repos');
    });

    test('should handle complex nested context_definitions with multiple levels', () => {
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  frontend_repos:
    - context_type: code
      name: ui-repo
  backend_repos:
    - context_type: code
      name: api-repo
  extension_repos:
    - context_type: code
      name: extension-repo
  all_code:
    - { "$ref": "context_definitions.frontend_repos" }
    - { "$ref": "context_definitions.backend_repos" }
    - { "$ref": "context_definitions.extension_repos" }
  knowledge_bases:
    - context_type: knowledge_base
      name: jira-kb
    - context_type: knowledge_base
      name: confluence-kb
  full_context:
    - { "$ref": "context_definitions.knowledge_bases" }
    - { "$ref": "context_definitions.all_code" }
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.full_context
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant = loaded.resources.assistants![0];

      expect(Array.isArray(assistant.context)).toBe(true);
      expect(assistant.context).toHaveLength(5);
      expect(assistant.context![0]).toEqual({ context_type: 'knowledge_base', name: 'jira-kb' });
      expect(assistant.context![1]).toEqual({ context_type: 'knowledge_base', name: 'confluence-kb' });
      expect(assistant.context![2]).toEqual({ context_type: 'code', name: 'ui-repo' });
      expect(assistant.context![3]).toEqual({ context_type: 'code', name: 'api-repo' });
      expect(assistant.context![4]).toEqual({ context_type: 'code', name: 'extension-repo' });
    });
  });

  describe('reference caching optimization', () => {
    test('should resolve same reference multiple times correctly', () => {
      // This test verifies that caching doesn't break correctness
      // when the same $ref is used multiple times
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: github_conn
      id: integration-456
      credential_type: Git
      project_name: test-project
resources:
  datasources:
    - name: Repo1
      type: code
      setting_id: $ref:imported.integrations.github_conn.id
    - name: Repo2
      type: code
      setting_id: $ref:imported.integrations.github_conn.id
    - name: Repo3
      type: code
      setting_id: $ref:imported.integrations.github_conn.id
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();
      const datasources = loaded.resources.datasources!;

      // All three datasources should have the same resolved integration ID
      expect(datasources[0].setting_id).toBe('integration-456');
      expect(datasources[1].setting_id).toBe('integration-456');
      expect(datasources[2].setting_id).toBe('integration-456');
    });

    test('should resolve deeply nested shared references correctly', () => {
      // Test that caching works with nested $refs that reference
      // the same underlying data multiple times
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  base_context:
    - context_type: code
      name: shared-repo
  extended_context_1:
    - { "$ref": "context_definitions.base_context" }
    - context_type: knowledge_base
      name: kb1
  extended_context_2:
    - { "$ref": "context_definitions.base_context" }
    - context_type: knowledge_base
      name: kb2
resources:
  assistants:
    - name: Assistant1
      description: Test 1
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.extended_context_1
    - name: Assistant2
      description: Test 2
      model: gpt-4o
      prompt: test.md
      context: $ref:context_definitions.extended_context_2
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistant1 = loaded.resources.assistants![0];
      const assistant2 = loaded.resources.assistants![1];

      // Both assistants should have correctly resolved contexts
      expect(assistant1.context).toHaveLength(2);
      expect(assistant1.context![0]).toEqual({ context_type: 'code', name: 'shared-repo' });
      expect(assistant1.context![1]).toEqual({ context_type: 'knowledge_base', name: 'kb1' });

      expect(assistant2.context).toHaveLength(2);
      expect(assistant2.context![0]).toEqual({ context_type: 'code', name: 'shared-repo' });
      expect(assistant2.context![1]).toEqual({ context_type: 'knowledge_base', name: 'kb2' });
    });

    test('should handle cache with complex nested references in arrays', () => {
      // Test caching when the same reference appears multiple times
      // in nested array structures
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
tool_definitions:
  - name: shared_tool
    description: A tool used multiple times
    input_schema:
      type: object
      properties:
        param1:
          type: string
resources:
  assistants:
    - name: Assistant1
      description: Test 1
      model: gpt-4o
      prompt: test.md
      toolkits:
        - toolkit: custom
          tools:
            - { "$ref": "tool_definitions.shared_tool" }
    - name: Assistant2
      description: Test 2
      model: gpt-4o
      prompt: test.md
      toolkits:
        - toolkit: custom
          tools:
            - { "$ref": "tool_definitions.shared_tool" }
    - name: Assistant3
      description: Test 3
      model: gpt-4o
      prompt: test.md
      toolkits:
        - toolkit: custom
          tools:
            - { "$ref": "tool_definitions.shared_tool" }
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const assistants = loaded.resources.assistants!;

      // All three assistants should have the same resolved tool
      expect(assistants[0].toolkits![0].tools[0]).toEqual({
        name: 'shared_tool',
        description: 'A tool used multiple times',
        input_schema: {
          type: 'object',
          properties: {
            param1: { type: 'string' },
          },
        },
      });

      expect(assistants[1].toolkits![0].tools[0]).toEqual({
        name: 'shared_tool',
        description: 'A tool used multiple times',
        input_schema: {
          type: 'object',
          properties: {
            param1: { type: 'string' },
          },
        },
      });

      expect(assistants[2].toolkits![0].tools[0]).toEqual({
        name: 'shared_tool',
        description: 'A tool used multiple times',
        input_schema: {
          type: 'object',
          properties: {
            param1: { type: 'string' },
          },
        },
      });
    });
  });

  describe('Object.assign optimization', () => {
    test('should correctly replace object with $ref resolution', () => {
      // Tests that Object.assign correctly replaces all keys
      // from the original $ref object with the resolved values
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
tool_definitions:
  - name: example_tool
    description: Example tool description
    input_schema:
      type: object
      properties:
        param1:
          type: string
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      toolkits:
        - toolkit: custom
          tools:
            - { "$ref": "tool_definitions.example_tool" }
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const tool = loaded.resources.assistants![0].toolkits![0].tools[0];

      // Should have all fields from the resolved tool
      expect(tool).toEqual({
        name: 'example_tool',
        description: 'Example tool description',
        input_schema: {
          type: 'object',
          properties: {
            param1: { type: 'string' },
          },
        },
      });

      // Should not have $ref field anymore
      expect('$ref' in tool).toBe(false);
    });

    test('should preserve object identity during resolution', () => {
      // Tests that the resolved object is the same instance (mutated in-place)
      // not a new object, which is important for parent references
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
datasource_defaults:
  standard_code:
    index_type: code
    embeddings_model: ada-002
resources:
  datasources:
    - name: MyRepo
      type: code
      $ref: datasource_defaults.standard_code
      link: https://example.com
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();
      const datasource = loaded.resources.datasources![0] as CodeDatasourceResource;

      // Should have merged defaults with explicit values
      expect(datasource.index_type).toBe('code');
      expect(datasource.embeddings_model).toBe('ada-002');
      expect(datasource.link).toBe('https://example.com');
      expect(datasource.name).toBe('MyRepo');

      // Should not have $ref field anymore
      expect('$ref' in datasource).toBe(false);
    });

    test('should handle undefined values correctly', () => {
      // Tests that undefined values in resolved object are not copied
      // (as per the current implementation's filter)
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: simple_conn
      id: integration-789
      credential_type: Bearer
resources:
  datasources:
    - name: SimpleRepo
      type: code
      setting_id: $ref:imported.integrations.simple_conn.id
  assistants: []
  workflows: []
`
      );

      const loaded = configLoader.loadConfig();

      // Should resolve correctly without adding undefined fields
      expect(loaded.resources.datasources![0].setting_id).toBe('integration-789');
    });
  });

  describe('array cloning optimization', () => {
    test('should correctly flatten arrays when resolving $ref to array', () => {
      // Tests that array references are correctly resolved and flattened
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  repos:
    - context_type: code
      name: repo1
    - context_type: code
      name: repo2
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - { "$ref": "context_definitions.repos" }
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const context = loaded.resources.assistants![0].context;

      expect(Array.isArray(context)).toBe(true);
      expect(context).toHaveLength(2);
      expect(context![0]).toEqual({ context_type: 'code', name: 'repo1' });
      expect(context![1]).toEqual({ context_type: 'code', name: 'repo2' });
    });

    test('should handle nested array references correctly', () => {
      // Tests that nested array structures are resolved properly
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  base:
    - context_type: code
      name: base1
  extended:
    - { "$ref": "context_definitions.base" }
    - context_type: knowledge_base
      name: kb1
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - { "$ref": "context_definitions.extended" }
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const context = loaded.resources.assistants![0].context;

      // Should correctly flatten nested structures
      expect(context).toHaveLength(2);
      expect(context![0]).toEqual({ context_type: 'code', name: 'base1' });
      expect(context![1]).toEqual({ context_type: 'knowledge_base', name: 'kb1' });
    });

    test('should preserve non-ref array items during resolution', () => {
      // Tests that items without $ref are preserved correctly
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
context_definitions:
  shared:
    - context_type: code
      name: shared1
resources:
  assistants:
    - name: Test Assistant
      description: Test
      model: gpt-4o
      prompt: test.md
      context:
        - context_type: knowledge_base
          name: direct1
        - { "$ref": "context_definitions.shared" }
        - context_type: knowledge_base
          name: direct2
  datasources: []
  workflows: []
`
      );
      fs.writeFileSync(path.join(tempDir, 'test.md'), 'Test prompt');

      const loaded = configLoader.loadConfig();
      const context = loaded.resources.assistants![0].context;

      // Should preserve direct items and correctly flatten $ref
      expect(context).toHaveLength(3);
      expect(context![0]).toEqual({ context_type: 'knowledge_base', name: 'direct1' });
      expect(context![1]).toEqual({ context_type: 'code', name: 'shared1' });
      expect(context![2]).toEqual({ context_type: 'knowledge_base', name: 'direct2' });
    });
  });

  describe('path building optimization', () => {
    test('should correctly report path in error messages for missing references', () => {
      // Tests that path building works correctly by checking error messages
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: test_conn
      id: integration-123
resources:
  datasources:
    - name: Test
      type: code
      setting_id: $ref:imported.integrations.test_conn.missing_field
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('imported.integrations.test_conn.missing_field');
    });

    test('should correctly report path for array search failures', () => {
      // Tests path building when searching in arrays
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
imported:
  integrations:
    - alias: existing_conn
      id: integration-456
resources:
  datasources:
    - name: Test
      type: code
      setting_id: $ref:imported.integrations.nonexistent.id
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('no item with alias="nonexistent" in "imported.integrations"');
    });

    test('should correctly report nested path in error messages', () => {
      // Tests path building with multiple levels
      fs.writeFileSync(
        path.join(tempDir, 'codemie.yaml'),
        `version: 1
project:
  name: test-project
resources:
  datasources:
    - name: Test
      type: code
      setting_id: $ref:imported.integrations.missing.id
  assistants: []
  workflows: []
`
      );

      expect(() => configLoader.loadConfig()).toThrow('imported" does not exist');
    });
  });
});
