/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { CodeMieClient, AssistantCreateParams } from 'codemie-sdk';

import * as deployModule from './deploy';
import { calculateChecksum } from './lib/checksumUtils';
import { CleanupManager } from './lib/cleanupManager';
import { createClient } from './lib/clientFactory';
import { calculateWorkflowConfigChecksum } from './lib/codemieConfigChecksums';
import { CodemieConfigLoader } from './lib/codemieConfigLoader';
import { TIMEOUTS_MS } from './lib/constants';
import { logger } from './lib/logger';
import { SkillNameIndex } from './lib/paginationUtils';
import { StateManager } from './lib/stateManager';
import type { AssistantResource, CodemieConfig, DatasourceResource, SkillResource } from './types/codemieConfig';

const { deployAssistants, deploySkills, deployWorkflows, deployDatasources, main, sortAssistantsByDependencies } =
  deployModule;

jest.mock('./lib/clientFactory');
jest.mock('./lib/cleanupManager');

const mockCreateClient = createClient as jest.MockedFunction<typeof createClient>;
const MockedCleanupManager = CleanupManager as jest.MockedClass<typeof CleanupManager>;

function buildClient(): CodeMieClient {
  const created: Array<{ id: string; name: string; slug?: string; created_date?: string }> = [];
  const service = {
    create: jest.fn((params: AssistantCreateParams) => {
      const id = `ast-${Math.random().toString(36).slice(2, 10)}`;
      created.push({
        id,
        name: params.name,
        slug: params.name.replaceAll(/\s+/g, '-'),
        created_date: new Date().toISOString(),
      });
      return Promise.resolve();
    }),
    update: jest.fn((_id: string, _params: AssistantCreateParams) => Promise.resolve()),
    get: jest.fn((id: string) => Promise.resolve(created.find((a) => a.id === id) || null)),
    getBySlug: jest.fn((slug: string) => Promise.resolve(created.find((a) => a.slug === slug) || null)),
    list: jest.fn(() => Promise.resolve(created)),
    getTools: jest.fn(),
    getTool: jest.fn(),
    createTool: jest.fn(),
    updateTool: jest.fn(),
    deleteTool: jest.fn(),
  };
  const skillsService = {
    attachToAssistant: jest.fn().mockResolvedValue({}),
    detachFromAssistant: jest.fn().mockResolvedValue({}),
    getAssistantSkills: jest.fn().mockResolvedValue([]),
    create: jest.fn(),
    update: jest.fn(),
    get: jest.fn(),
    delete: jest.fn(),
    list: jest.fn().mockResolvedValue([]),
    listCompanionFiles: jest.fn().mockResolvedValue([]),
  };
  return { assistants: service, skills: skillsService } as unknown as CodeMieClient;
}

function baseConfig(): CodemieConfig {
  return {
    version: '1',
    project: { name: 'proj', description: '' },
    environment: {
      codemie_api_url: 'https://api.example',
      auth_server_url: 'https://auth.example',
      auth_realm_name: 'realm',
      client_id: 'cid',
      client_secret: 'sec',
    },
    imported: { assistants: [], datasources: [], skills: [], integrations: [] },
    resources: { assistants: [], datasources: [], workflows: [] },
  };
}

// Helper to create temp project structure with prompt/config files
function setupTempProject(): { dir: string; loader: CodemieConfigLoader; state: StateManager } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apply-test-'));
  fs.mkdirSync(path.join(dir, 'system_prompts'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'configs'), { recursive: true });
  const appConfig = {
    rootDir: dir,
    codemieConfig: 'codemie.yaml',
    codemieState: 'state.json',
    backupsDirectory: 'backups',
  };
  return { dir, loader: new CodemieConfigLoader(appConfig), state: new StateManager(appConfig) };
}

describe('deployAssistants', () => {
  let dir: string;
  let loader: CodemieConfigLoader;
  let state: StateManager;
  let client: CodeMieClient;

  beforeEach(() => {
    const setup = setupTempProject();
    dir = setup.dir;
    loader = setup.loader;
    state = setup.state;
    client = buildClient();

    client.assistants.get = jest.fn(client.assistants.get);
    client.assistants.update = jest.fn(client.assistants.update);
    client.assistants.create = jest.fn(client.assistants.create);
  });

  it('should create assistant when absent from state', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'A1',
      description: 'desc',
      prompt: 'system_prompts/a1.prompt.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 0 });
    expect(state.getAssistantState('A1')).toBeDefined();
  });

  it.each([
    false,
    true,
  ])('does not recover or write state after create validation fails (stale state: %s)', async (stale) => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'Rejected',
      description: 'desc',
      prompt: 'system_prompts/rejected.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'NEW_PROMPT');
    cfg.resources.assistants = [assistant];
    if (stale) {
      state.updateAssistantState(assistant.name, 'old-id', 'OLD_PROMPT', assistant);
    }
    const before = state.getAssistantState(assistant.name);
    if (stale) {
      (client.assistants.get as jest.Mock).mockRejectedValue(
        Object.assign(new Error('Not found'), { statusCode: 404 })
      );
    }
    (client.assistants.create as jest.Mock).mockResolvedValue({
      validation: { has_missing_integrations: true, message: 'Configure tools' },
    });
    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats).toEqual({ created: 0, updated: 0, unchanged: 0, failed: 1 });
    expect(state.getAssistantState(assistant.name)).toEqual(before);
    expect(client.assistants.list).not.toHaveBeenCalled();
    expect(client.assistants.update).not.toHaveBeenCalled();
  });

  it.each([400, 401, 403, 422])('does not perform recovery lookup after HTTP %i', async (statusCode) => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'Rejected request',
      description: 'desc',
      prompt: 'system_prompts/rejected.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    (client.assistants.create as jest.Mock).mockRejectedValue(
      Object.assign(new Error('Rejected'), { statusCode, response: { detail: 'Original error' } })
    );
    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.failed).toBe(1);
    expect(state.getAssistantState(assistant.name)).toBeUndefined();
    expect(client.assistants.list).not.toHaveBeenCalled();
    expect(client.assistants.update).not.toHaveBeenCalled();
  });

  it('does not record a rejected update as synchronized', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'Rejected update',
      description: 'desc',
      prompt: 'system_prompts/rejected.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'NEW_PROMPT');
    cfg.resources.assistants = [assistant];
    state.updateAssistantState(assistant.name, 'existing-id', 'OLD_PROMPT', assistant);
    const before = state.getAssistantState(assistant.name);
    (client.assistants.get as jest.Mock).mockResolvedValue({ id: 'existing-id' });
    (client.assistants.update as jest.Mock).mockResolvedValue({
      validation: { has_missing_integrations: true, message: 'Configure tools' },
    });
    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.failed).toBe(1);
    expect(stats.updated).toBe(0);
    expect(state.getAssistantState(assistant.name)).toEqual(before);
  });

  it('does not write state after a recovered assistant rejects its update', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'Rejected recovery',
      description: 'desc',
      prompt: 'system_prompts/rejected.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    (client.assistants.create as jest.Mock).mockRejectedValue(
      Object.assign(new Error('Already exists'), { statusCode: 409 })
    );
    (client.assistants.list as jest.Mock).mockResolvedValue([{ id: 'existing-id', name: assistant.name }]);
    (client.assistants.update as jest.Mock).mockResolvedValue({ validation: { has_missing_integrations: true } });
    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.failed).toBe(1);
    expect(stats.updated).toBe(0);
    expect(state.getAssistantState(assistant.name)).toBeUndefined();
  });

  it('should update assistant when prompt content changed', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'A2',
      description: 'desc',
      prompt: 'system_prompts/a2.prompt.md',
      model: 'gpt-4',
    };
    // previous deploy with OLD_PROMPT
    const oldAssistant: AssistantResource = {
      name: 'A2',
      description: 'desc',
      prompt: 'system_prompts/a2.prompt.md',
      model: 'gpt-4',
    };
    state.updateAssistantState('A2', 'existing-id', 'OLD_PROMPT', oldAssistant);
    fs.writeFileSync(path.join(dir, assistant.prompt), 'NEW_PROMPT');
    cfg.resources.assistants = [assistant];

    // Seed client storage with existing assistant to simulate platform presence
    await client.assistants.create({
      name: 'A2',
      description: 'desc',
      llm_model_type: 'gpt-4',
      system_prompt: 'OLD_PROMPT',
      project: 'proj',
      conversation_starters: [],
      toolkits: [],
      context: [],
      mcp_servers: [],
      assistant_ids: [],
      shared: true,
      prompt_variables: [],
    });
    // Replace generated id with expected one for deterministic update path
    const createdList = await client.assistants.list({});
    const lastCreated = createdList.at(-1);
    if (lastCreated) {
      Object.defineProperty(lastCreated, 'id', { value: 'existing-id', writable: true });
    }

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.updated).toBe(1);
    const st = state.getAssistantState('A2');
    expect(st?.promptChecksum).toBe(calculateChecksum('NEW_PROMPT'));
  });

  it('should mark assistant unchanged when checksums match', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'A3',
      description: 'desc',
      prompt: 'system_prompts/a3.prompt.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');

    await client.assistants.create({
      name: 'A3',
      description: 'desc',
      llm_model_type: 'gpt-4',
      system_prompt: 'PROMPT',
      project: 'proj',
      conversation_starters: [],
      toolkits: [],
      context: [],
      mcp_servers: [],
      assistant_ids: [],
      shared: true,
      prompt_variables: [],
    });
    const createdList = await client.assistants.list({});
    const lastCreated = createdList.at(-1);
    if (lastCreated) {
      Object.defineProperty(lastCreated, 'id', { value: 'id-3', writable: true });
    }

    state.updateAssistantState('A3', 'id-3', 'PROMPT', assistant);

    cfg.resources.assistants = [assistant];

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.unchanged).toBe(1);
    expect(stats.updated).toBe(0);
    expect(stats.created).toBe(0);
  });

  it('should throw error when sub-assistant missing', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'A4',
      description: 'desc',
      prompt: 'system_prompts/a4.prompt.md',
      model: 'gpt-4',
      sub_assistants: ['MissingSub'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    await expect(deployAssistants(cfg, client, loader, state)).rejects.toThrow(
      'Sub-assistant "MissingSub" referenced by "A4" not found in config'
    );
  });

  it('should attach skills to assistant after creation', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'SkillAssistant',
      description: 'desc',
      prompt: 'system_prompts/skill-ast.prompt.md',
      model: 'gpt-4',
      skills: ['my-skill'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    cfg.resources.skills = [{ name: 'my-skill', description: 'A skill', file: 'skills/my-skill.skill.md' }];

    state.updateSkillState('my-skill', 'skill-uuid-123', 'content', {
      name: 'my-skill',
      description: 'A skill',
      file: 'skills/my-skill.skill.md',
    });

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.created).toBe(1);
    expect(client.skills.attachToAssistant).toHaveBeenCalledWith(expect.any(String), 'skill-uuid-123');
  });

  it('should attach imported skills to assistant without state entry', async () => {
    const cfg = baseConfig();
    cfg.imported.skills = [{ name: 'marketplace-skill', id: 'skill-imported-id' }];
    const assistant: AssistantResource = {
      name: 'ImportedSkillAssistant',
      description: 'desc',
      prompt: 'system_prompts/imported-skill-ast.prompt.md',
      model: 'gpt-4',
      skills: ['marketplace-skill'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.created).toBe(1);
    expect(client.skills.attachToAssistant).toHaveBeenCalledWith(expect.any(String), 'skill-imported-id');
  });

  it('should attach imported skill ID instead of stale state ID', async () => {
    const cfg = baseConfig();
    cfg.imported.skills = [{ name: 'marketplace-skill', id: 'skill-imported-id' }];
    const assistant: AssistantResource = {
      name: 'ImportedSkillAssistant',
      description: 'desc',
      prompt: 'system_prompts/imported-skill-ast.prompt.md',
      model: 'gpt-4',
      skills: ['marketplace-skill'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    state.updateSkillState('marketplace-skill', 'stale-state-id', 'content', {
      name: 'marketplace-skill',
      description: 'Previously managed skill',
      file: 'skills/marketplace-skill.skill.md',
    });

    const stats = await deployAssistants(cfg, client, loader, state);

    expect(stats.created).toBe(1);
    expect(client.skills.attachToAssistant).toHaveBeenCalledWith(expect.any(String), 'skill-imported-id');
    expect(client.skills.attachToAssistant).not.toHaveBeenCalledWith(expect.any(String), 'stale-state-id');
  });

  it('should fail deploy when skill is missing from state and imported.skills', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'MissingSkillAssistant',
      description: 'desc',
      prompt: 'system_prompts/missing-skill-ast.prompt.md',
      model: 'gpt-4',
      skills: ['missing-skill'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    const stats = await deployAssistants(cfg, client, loader, state);

    expect(stats.failed).toBe(1);
    expect(stats.created).toBe(0);
  });

  it('should attach skills to assistant after update', async () => {
    const cfg = baseConfig();
    cfg.resources.skills = [{ name: 'upd-skill', description: 'A skill', file: 'skills/upd-skill.skill.md' }];
    const assistant: AssistantResource = {
      name: 'SkillUpdateAssistant',
      description: 'desc',
      prompt: 'system_prompts/skill-upd.prompt.md',
      model: 'gpt-4',
      skills: ['upd-skill'],
    };

    state.updateSkillState('upd-skill', 'skill-uuid-456', 'content', {
      name: 'upd-skill',
      description: 'A skill',
      file: 'skills/upd-skill.skill.md',
    });

    const oldAssistant: AssistantResource = {
      name: 'SkillUpdateAssistant',
      description: 'desc',
      prompt: 'system_prompts/skill-upd.prompt.md',
      model: 'gpt-4',
      skills: ['upd-skill'],
    };
    state.updateAssistantState('SkillUpdateAssistant', 'existing-ast-id', 'OLD_PROMPT', oldAssistant);
    fs.writeFileSync(path.join(dir, assistant.prompt), 'NEW_PROMPT');
    cfg.resources.assistants = [assistant];

    await client.assistants.create({
      name: 'SkillUpdateAssistant',
      description: 'desc',
      llm_model_type: 'gpt-4',
      system_prompt: 'OLD_PROMPT',
      project: 'proj',
      conversation_starters: [],
      toolkits: [],
      context: [],
      mcp_servers: [],
      assistant_ids: [],
      shared: true,
      prompt_variables: [],
    });
    const createdList = await client.assistants.list({});
    const lastCreated = createdList.at(-1);
    if (lastCreated) {
      Object.defineProperty(lastCreated, 'id', { value: 'existing-ast-id', writable: true });
    }

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.updated).toBe(1);
    expect(client.skills.attachToAssistant).toHaveBeenCalledWith('existing-ast-id', 'skill-uuid-456');
  });

  it('should skip skill sync entirely when skills field is not defined in config', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'NoSkillAssistant',
      description: 'desc',
      prompt: 'system_prompts/no-skill.prompt.md',
      model: 'gpt-4',
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    await deployAssistants(cfg, client, loader, state);
    expect(client.skills.getAssistantSkills).not.toHaveBeenCalled();
    expect(client.skills.attachToAssistant).not.toHaveBeenCalled();
    expect(client.skills.detachFromAssistant).not.toHaveBeenCalled();
  });

  it('should detach all skills when skills is explicitly empty array', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'EmptySkillsAssistant',
      description: 'desc',
      prompt: 'system_prompts/empty-skills.prompt.md',
      model: 'gpt-4',
      skills: [],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    (client.skills.getAssistantSkills as jest.Mock).mockResolvedValueOnce([
      { id: 'old-skill-id', name: 'leftover-skill' },
    ]);

    await deployAssistants(cfg, client, loader, state);
    expect(client.skills.getAssistantSkills).toHaveBeenCalled();
    expect(client.skills.detachFromAssistant).toHaveBeenCalledWith(expect.any(String), 'old-skill-id');
    expect(client.skills.attachToAssistant).not.toHaveBeenCalled();
  });

  it('should handle already-attached skill gracefully', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'AlreadyAttachedAssistant',
      description: 'desc',
      prompt: 'system_prompts/attached.prompt.md',
      model: 'gpt-4',
      skills: ['attached-skill'],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];
    cfg.resources.skills = [{ name: 'attached-skill', description: 'A skill', file: 'skills/attached-skill.skill.md' }];

    state.updateSkillState('attached-skill', 'skill-uuid-789', 'content', {
      name: 'attached-skill',
      description: 'A skill',
      file: 'skills/attached-skill.skill.md',
    });

    (client.skills.attachToAssistant as jest.Mock).mockRejectedValueOnce(new Error('already attached'));

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.created).toBe(1);
    expect(stats.failed).toBe(0);
  });

  it('should detach skills removed from assistant config', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'DetachAssistant',
      description: 'desc',
      prompt: 'system_prompts/detach.prompt.md',
      model: 'gpt-4',
      skills: [],
    };

    state.updateAssistantState('DetachAssistant', 'detach-ast-id', 'PROMPT', assistant);
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    await client.assistants.create({
      name: 'DetachAssistant',
      description: 'desc',
      llm_model_type: 'gpt-4',
      system_prompt: 'PROMPT',
      project: 'proj',
      conversation_starters: [],
      toolkits: [],
      context: [],
      mcp_servers: [],
      assistant_ids: [],
      shared: true,
      prompt_variables: [],
    });
    const createdList = await client.assistants.list({});
    const lastCreated = createdList.at(-1);
    if (lastCreated) {
      Object.defineProperty(lastCreated, 'id', { value: 'detach-ast-id', writable: true });
    }

    // Simulate platform has a skill attached that's no longer in config
    (client.skills.getAssistantSkills as jest.Mock).mockResolvedValueOnce([
      { id: 'old-skill-id', name: 'removed-skill' },
    ]);

    await deployAssistants(cfg, client, loader, state);
    expect(client.skills.detachFromAssistant).toHaveBeenCalledWith('detach-ast-id', 'old-skill-id');
    expect(client.skills.attachToAssistant).not.toHaveBeenCalled();
  });

  it('should skip already-attached skills and only attach new ones', async () => {
    const cfg = baseConfig();
    cfg.resources.skills = [
      { name: 'existing-skill', description: 'existing', file: 'skills/existing.skill.md' },
      { name: 'new-skill', description: 'new', file: 'skills/new.skill.md' },
    ];
    const assistant: AssistantResource = {
      name: 'PartialAttachAssistant',
      description: 'desc',
      prompt: 'system_prompts/partial.prompt.md',
      model: 'gpt-4',
      skills: ['existing-skill', 'new-skill'],
    };

    state.updateSkillState('existing-skill', 'skill-existing-id', 'content', {
      name: 'existing-skill',
      description: 'existing',
      file: 'skills/existing.skill.md',
    });
    state.updateSkillState('new-skill', 'skill-new-id', 'content', {
      name: 'new-skill',
      description: 'new',
      file: 'skills/new.skill.md',
    });

    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    // Simulate platform already has one skill attached
    (client.skills.getAssistantSkills as jest.Mock).mockResolvedValueOnce([
      { id: 'skill-existing-id', name: 'existing-skill' },
    ]);

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.created).toBe(1);
    // Should only attach the new skill, not the existing one
    expect(client.skills.attachToAssistant).toHaveBeenCalledTimes(1);
    expect(client.skills.attachToAssistant).toHaveBeenCalledWith(expect.any(String), 'skill-new-id');
    expect(client.skills.detachFromAssistant).not.toHaveBeenCalled();
  });

  it('should handle already-detached skill gracefully', async () => {
    const cfg = baseConfig();
    const assistant: AssistantResource = {
      name: 'DetachGraceAssistant',
      description: 'desc',
      prompt: 'system_prompts/detach-grace.prompt.md',
      model: 'gpt-4',
      skills: [],
    };
    fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
    cfg.resources.assistants = [assistant];

    (client.skills.getAssistantSkills as jest.Mock).mockResolvedValueOnce([
      { id: 'ghost-skill-id', name: 'ghost-skill' },
    ]);
    (client.skills.detachFromAssistant as jest.Mock).mockRejectedValueOnce(new Error('not found'));

    const stats = await deployAssistants(cfg, client, loader, state);
    expect(stats.created).toBe(1);
    expect(stats.failed).toBe(0);
  });

  describe('create-failure recovery', () => {
    function slugAssistant(): AssistantResource {
      const assistant: AssistantResource = {
        name: 'Recover Me',
        slug: 'recover-me',
        description: 'desc',
        prompt: 'system_prompts/recover.prompt.md',
        model: 'gpt-4',
      };
      fs.writeFileSync(path.join(dir, assistant.prompt), 'PROMPT');
      return assistant;
    }

    it('counts updated when create fails and getBySlug finds the assistant', async () => {
      const cfg = baseConfig();
      cfg.resources.assistants = [slugAssistant()];
      client.assistants.create = jest.fn().mockRejectedValue(new Error('conflict'));
      client.assistants.getBySlug = jest.fn().mockResolvedValue({ id: 'ast-existing', name: 'Recover Me' });

      const stats = await deployAssistants(cfg, client, loader, state);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
      expect(client.assistants.update).toHaveBeenCalledWith('ast-existing', expect.anything());
      expect(state.getAssistantState('Recover Me')?.id).toBe('ast-existing');
    });

    it('counts updated when getBySlug throws and name lookup finds the assistant', async () => {
      const cfg = baseConfig();
      cfg.resources.assistants = [slugAssistant()];
      client.assistants.create = jest.fn().mockRejectedValue(new Error('conflict'));
      client.assistants.getBySlug = jest.fn().mockRejectedValue(new Error('slug lookup failed'));
      client.assistants.list = jest.fn().mockResolvedValue([{ id: 'ast-by-name', name: 'Recover Me' }]);

      const stats = await deployAssistants(cfg, client, loader, state);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
      expect(client.assistants.update).toHaveBeenCalledWith('ast-by-name', expect.anything());
    });

    it('counts failed and logs the create error when the assistant cannot be found', async () => {
      const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
      try {
        const cfg = baseConfig();
        cfg.resources.assistants = [slugAssistant()];
        client.assistants.create = jest.fn().mockRejectedValue(new Error('original create failure'));
        client.assistants.getBySlug = jest.fn().mockResolvedValue(null);
        client.assistants.list = jest.fn().mockResolvedValue([]);

        const stats = await deployAssistants(cfg, client, loader, state);

        expect(stats).toEqual({ created: 0, updated: 0, unchanged: 0, failed: 1 });
        expect(errorSpy).toHaveBeenCalledWith('     original create failure');
      } finally {
        errorSpy.mockRestore();
      }
    });
  });
});

describe('main', () => {
  let dir: string;
  let originalExit: typeof process.exit;
  let originalEnv: NodeJS.ProcessEnv;
  let originalCwd: string;
  let consoleLogSpy: jest.SpyInstance;
  let consoleErrorSpy: jest.SpyInstance;
  let flagsConfig: {
    appConfig: { rootDir: string; codemieConfig: string; codemieState: string; backupsDirectory: string };
    prune?: boolean;
    skipDatasources?: boolean;
  };

  beforeEach(() => {
    originalCwd = process.cwd();
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apply-main-test-'));
    fs.mkdirSync(path.join(dir, 'system_prompts'), { recursive: true });

    // Mock process.exit
    originalExit = process.exit;
    process.exit = jest.fn() as unknown as typeof process.exit;

    // Mock console to reduce noise
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    // Save original env
    originalEnv = { ...process.env };

    // Reset mocks
    jest.clearAllMocks();

    // Setup default mocks for createClient and CleanupManager
    const mockClient = {
      assistants: { list: jest.fn().mockResolvedValue([]) },
      datasources: { list: jest.fn().mockResolvedValue([]) },
      workflows: { list: jest.fn().mockResolvedValue([]) },
      skills: { list: jest.fn().mockResolvedValue([]) },
    };
    mockCreateClient.mockResolvedValue(mockClient as unknown as CodeMieClient);

    const mockCleanup = {
      findOrphanedResources: jest.fn().mockReturnValue({ assistants: [], datasources: [], workflows: [], skills: [] }),
      deleteOrphanedResources: jest
        .fn()
        .mockResolvedValue({ deleted: { assistants: [], datasources: [], workflows: [], skills: [] }, errors: [] }),
    };
    MockedCleanupManager.mockImplementation(() => mockCleanup as unknown as CleanupManager);

    // Create minimal codemie.yaml
    const minimalConfig: CodemieConfig = {
      version: '1',
      project: { name: 'test-proj', description: 'Test Project' },
      environment: {
        codemie_api_url: 'https://api.example',
        auth_server_url: 'https://auth.example',
        auth_realm_name: 'realm',
        client_id: 'cid',
        client_secret: 'sec',
      },
      imported: { assistants: [], datasources: [], skills: [], integrations: [] },
      resources: { assistants: [], datasources: [], workflows: [] },
    };
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(minimalConfig));

    // Change to test directory
    process.chdir(dir);

    flagsConfig = {
      appConfig: {
        rootDir: process.cwd(),
        codemieConfig: 'codemie.yaml',
        codemieState: 'state.json',
        backupsDirectory: 'backups',
      },
    };
  });

  afterEach(() => {
    // Restore original directory first
    if (process.cwd() !== originalCwd) {
      try {
        process.chdir(originalCwd);
      } catch {
        // Directory may not exist anymore, ignore
      }
    }

    process.exit = originalExit;
    process.env = originalEnv;
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
    jest.restoreAllMocks();
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it('should successfully deploy with no resources', async () => {
    await main(flagsConfig);

    expect(process.exit).toHaveBeenCalledWith(0);
  });

  it('should exit with code 1 on deployment failure', async () => {
    // Create assistant to trigger deployment
    const cfg: CodemieConfig = JSON.parse(fs.readFileSync(path.join(dir, 'codemie.yaml'), 'utf8'));
    cfg.resources.assistants = [
      {
        name: 'TestAssistant',
        description: 'Test',
        prompt: 'system_prompts/test.md',
        model: 'gpt-4',
      },
    ];
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));
    fs.writeFileSync(path.join(dir, 'system_prompts/test.md'), 'TEST_PROMPT');

    // Make client throw error on assistant creation to trigger failure
    const mockClientWithError = {
      assistants: {
        list: jest.fn().mockResolvedValue([]),
        create: jest.fn().mockRejectedValue(new Error('API Error')),
      },
      datasources: { list: jest.fn().mockResolvedValue([]) },
      workflows: { list: jest.fn().mockResolvedValue([]) },
      skills: { list: jest.fn().mockResolvedValue([]) },
    };
    mockCreateClient.mockResolvedValue(mockClientWithError as unknown as CodeMieClient);

    await deployModule.main(flagsConfig);

    expect(process.exit).toHaveBeenCalledWith(1);
  });

  it('should handle errors and exit with code 1', async () => {
    // Remove config to trigger error
    fs.rmSync(path.join(dir, 'codemie.yaml'));

    await main(flagsConfig);

    expect(process.exit).toHaveBeenCalledWith(1);
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('should reject an out-of-range skill description before calling the API', async () => {
    const cfg: CodemieConfig = JSON.parse(fs.readFileSync(path.join(dir, 'codemie.yaml'), 'utf8'));
    cfg.resources.skills = [{ name: 'bad-skill', description: 'too short', file: 'skills/bad-skill.skill.md' }];
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));
    fs.mkdirSync(path.join(dir, 'skills'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'skills/bad-skill.skill.md'), '# bad skill content, long enough');

    await main(flagsConfig);

    expect(process.exit).toHaveBeenCalledWith(1);
    expect(mockCreateClient).not.toHaveBeenCalled();
    const errorOutput = consoleErrorSpy.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(errorOutput).toContain('Skill "bad-skill" description length is 9 characters');
    expect(errorOutput).toContain('Allowed range: 10-1000 characters');
  });

  describe('--skip-datasources', () => {
    let dsClient: CodeMieClient;
    let cleanup: {
      findOrphanedResources: jest.Mock;
      deleteOrphanedResources: jest.Mock;
    };

    function readStateDatasources(): string {
      const raw = JSON.parse(fs.readFileSync(path.join(dir, 'state.json'), 'utf8')) as {
        resources: { datasources: unknown };
      };
      return JSON.stringify(raw.resources.datasources);
    }

    function loggedText(): string {
      return consoleLogSpy.mock.calls.map((call: unknown[]) => call.map(String).join(' ')).join('\n');
    }

    beforeEach(() => {
      const cfg: CodemieConfig = JSON.parse(fs.readFileSync(path.join(dir, 'codemie.yaml'), 'utf8'));
      cfg.resources.datasources = [
        {
          name: 'cfg-ds',
          type: 'knowledge_base_file',
          embeddings_model: 'amazon.titan-embed-text-v2:0',
          shared_with_project: true,
          description: 'config datasource',
        } as DatasourceResource,
      ];
      fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));

      const stateManager = new StateManager(flagsConfig.appConfig);
      stateManager.updateDatasourceState('old-ds', 'ds-old-id', {
        name: 'old-ds',
        type: 'knowledge_base_file',
      } as DatasourceResource);
      stateManager.updateAssistantState('old-ast', 'ast-old-id', 'prompt', {
        name: 'old-ast',
        prompt: 'x.md',
        model: 'gpt-4',
      } as AssistantResource);

      const listed: Array<{ id: string; name: string }> = [];
      dsClient = {
        assistants: { list: jest.fn().mockResolvedValue([]) },
        datasources: {
          get: jest.fn().mockRejectedValue(new Error('not found')),
          create: jest.fn((params: { name: string }) => {
            listed.push({ id: 'ds-created-id', name: params.name });
            return Promise.resolve({});
          }),
          update: jest.fn().mockResolvedValue({}),
          delete: jest.fn().mockResolvedValue({}),
          list: jest.fn(() => Promise.resolve(listed)),
        },
        workflows: { list: jest.fn().mockResolvedValue([]) },
        skills: { list: jest.fn().mockResolvedValue([]) },
      } as unknown as CodeMieClient;
      mockCreateClient.mockResolvedValue(dsClient);

      cleanup = {
        findOrphanedResources: jest
          .fn()
          .mockReturnValue({ assistants: ['old-ast'], datasources: ['old-ds'], workflows: [], skills: [] }),
        deleteOrphanedResources: jest
          .fn()
          .mockResolvedValue({ deleted: { assistants: [], datasources: [], workflows: [], skills: [] }, errors: [] }),
      };
      MockedCleanupManager.mockImplementation(() => cleanup as unknown as CleanupManager);
    });

    it('skips datasource create/update/delete and keeps datasource state untouched', async () => {
      const before = readStateDatasources();

      await main({ ...flagsConfig, prune: true, skipDatasources: true });

      expect(process.exit).toHaveBeenCalledWith(0);
      expect(dsClient.datasources.create).not.toHaveBeenCalled();
      expect(dsClient.datasources.update).not.toHaveBeenCalled();
      expect(dsClient.datasources.delete).not.toHaveBeenCalled();
      expect(cleanup.deleteOrphanedResources).toHaveBeenCalledWith(
        expect.objectContaining({ assistants: ['old-ast'], datasources: [] })
      );
      expect(readStateDatasources()).toBe(before);
      const text = loggedText();
      expect(text).toContain('Skipped (--skip-datasources): 1 datasource(s)');
      expect(text).toContain('1 orphaned datasource(s) skipped (--skip-datasources)');
    });

    it('deploys the datasource on a later run without the flag', async () => {
      await main({ ...flagsConfig, skipDatasources: true });
      expect(dsClient.datasources.create).not.toHaveBeenCalled();

      await main(flagsConfig);

      expect(dsClient.datasources.create).toHaveBeenCalledTimes(1);
      expect(dsClient.datasources.create).toHaveBeenCalledWith(expect.objectContaining({ name: 'cfg-ds' }));
    });

    it('still skips orphan deletion under SAMPLE_DEPLOY=1 with the flag', async () => {
      process.env.SAMPLE_DEPLOY = '1';

      await main({ ...flagsConfig, prune: true, skipDatasources: true });

      expect(cleanup.deleteOrphanedResources).not.toHaveBeenCalled();
      expect(dsClient.datasources.create).not.toHaveBeenCalled();
    });
  });
});

describe('sortAssistantsByDependencies', () => {
  it('should sort assistants with sub_assistants after their dependencies', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Orchestrator',
        description: 'Main orchestrator',
        prompt: 'orchestrator.md',
        model: 'gpt-4',
        sub_assistants: ['Assistant A', 'Assistant B'],
      },
      {
        name: 'Assistant A',
        description: 'Helper A',
        prompt: 'helper-a.md',
        model: 'gpt-4',
      },
      {
        name: 'Assistant B',
        description: 'Helper B',
        prompt: 'helper-b.md',
        model: 'gpt-4',
      },
    ];

    const sorted = sortAssistantsByDependencies(assistants);

    expect(sorted).toHaveLength(3);
    expect(sorted[0].name).toBe('Assistant A');
    expect(sorted[1].name).toBe('Assistant B');
    expect(sorted[2].name).toBe('Orchestrator');
  });

  it('should handle nested dependencies', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Level 3',
        description: 'Top level',
        prompt: 'level3.md',
        model: 'gpt-4',
        sub_assistants: ['Level 2'],
      },
      {
        name: 'Level 2',
        description: 'Middle level',
        prompt: 'level2.md',
        model: 'gpt-4',
        sub_assistants: ['Level 1'],
      },
      {
        name: 'Level 1',
        description: 'Base level',
        prompt: 'level1.md',
        model: 'gpt-4',
      },
    ];

    const sorted = sortAssistantsByDependencies(assistants);

    expect(sorted).toHaveLength(3);
    expect(sorted[0].name).toBe('Level 1');
    expect(sorted[1].name).toBe('Level 2');
    expect(sorted[2].name).toBe('Level 3');
  });

  it('should handle assistants without dependencies', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Assistant A',
        description: 'Independent A',
        prompt: 'a.md',
        model: 'gpt-4',
      },
      {
        name: 'Assistant B',
        description: 'Independent B',
        prompt: 'b.md',
        model: 'gpt-4',
      },
    ];

    const sorted = sortAssistantsByDependencies(assistants);

    expect(sorted).toHaveLength(2);
    // Order should be preserved for independent assistants
    expect(sorted.map((a) => a.name)).toEqual(['Assistant A', 'Assistant B']);
  });

  it('should throw error on circular dependency', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Assistant A',
        description: 'A',
        prompt: 'a.md',
        model: 'gpt-4',
        sub_assistants: ['Assistant B'],
      },
      {
        name: 'Assistant B',
        description: 'B',
        prompt: 'b.md',
        model: 'gpt-4',
        sub_assistants: ['Assistant A'],
      },
    ];

    expect(() => sortAssistantsByDependencies(assistants)).toThrow('Circular dependency detected');
  });

  it('should throw error when sub-assistant not found', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Orchestrator',
        description: 'Main',
        prompt: 'orchestrator.md',
        model: 'gpt-4',
        sub_assistants: ['NonExistent'],
      },
    ];

    expect(() => sortAssistantsByDependencies(assistants)).toThrow(
      'Sub-assistant "NonExistent" referenced by "Orchestrator" not found in config'
    );
  });

  it('should handle mixed dependencies', () => {
    const assistants: AssistantResource[] = [
      {
        name: 'Orchestrator',
        description: 'Main',
        prompt: 'orch.md',
        model: 'gpt-4',
        sub_assistants: ['Helper A', 'Helper B'],
      },
      {
        name: 'Helper A',
        description: 'A',
        prompt: 'a.md',
        model: 'gpt-4',
        sub_assistants: ['Base'],
      },
      {
        name: 'Helper B',
        description: 'B',
        prompt: 'b.md',
        model: 'gpt-4',
      },
      {
        name: 'Base',
        description: 'Base',
        prompt: 'base.md',
        model: 'gpt-4',
      },
      {
        name: 'Independent',
        description: 'Independent',
        prompt: 'indep.md',
        model: 'gpt-4',
      },
    ];

    const sorted = sortAssistantsByDependencies(assistants);

    expect(sorted).toHaveLength(5);

    // Base must be before Helper A
    const baseIndex = sorted.findIndex((a) => a.name === 'Base');
    const helperAIndex = sorted.findIndex((a) => a.name === 'Helper A');
    expect(baseIndex).toBeLessThan(helperAIndex);

    // Helper A and Helper B must be before Orchestrator
    const helperBIndex = sorted.findIndex((a) => a.name === 'Helper B');
    const orchIndex = sorted.findIndex((a) => a.name === 'Orchestrator');
    expect(helperAIndex).toBeLessThan(orchIndex);
    expect(helperBIndex).toBeLessThan(orchIndex);
  });
});

describe('Workflow assistant_name resolution logic', () => {
  interface WorkflowAssistant {
    id: string;
    assistant_name?: string;
    assistant_id?: string;
    model?: string;
    system_prompt?: string;
    name?: string;
  }

  /**
   * Current (buggy) logic from apply.ts line 418-421
   */
  function isInlineAssistantBuggy(assistant: WorkflowAssistant): boolean {
    // Bug: treats assistant with model OR system_prompt as inline, even if has assistant_name
    return Boolean(assistant.model || assistant.system_prompt);
  }

  /**
   * Correct logic: inline only if has model+system_prompt AND NO assistant_name
   */
  function isInlineAssistantCorrect(assistant: WorkflowAssistant): boolean {
    // If has assistant_name, it's a REFERENCE (even with model/system_prompt overrides)
    if (assistant.assistant_name) {
      return false;
    }

    // If no assistant_name, it's inline only if has model AND system_prompt
    return Boolean(assistant.model && assistant.system_prompt);
  }

  describe('Current buggy logic', () => {
    it('should incorrectly treat reference with model override as inline', () => {
      const assistant: WorkflowAssistant = {
        id: 'jira_test_mgmt',
        assistant_name: 'Jira Test Management Assistant',
        model: 'gpt-4.1', // Model override
      };

      const result = isInlineAssistantBuggy(assistant);

      // Bug: returns true because assistant.model exists
      expect(result).toBe(true);

      // This causes the assistant to be skipped during resolution
      // So assistant_name never gets converted to assistant_id
    });

    it('should incorrectly skip assistants with only assistant_name and model', () => {
      const assistant: WorkflowAssistant = {
        id: 'checker',
        assistant_name: 'Checklist Generator Assistant',
        model: 'gpt-4.1',
      };

      expect(isInlineAssistantBuggy(assistant)).toBe(true); // Wrong!
    });
  });

  describe('Correct logic', () => {
    it('should correctly identify reference assistant with model override', () => {
      const assistant: WorkflowAssistant = {
        id: 'jira_test_mgmt',
        assistant_name: 'Jira Test Management Assistant',
        model: 'gpt-4.1', // Model override - but still a reference!
      };

      const result = isInlineAssistantCorrect(assistant);

      // Correct: returns false because has assistant_name
      expect(result).toBe(false);
    });

    it('should correctly identify inline assistant', () => {
      const assistant: WorkflowAssistant = {
        id: 'webhook_parser',
        model: 'gpt-4o-mini',
        name: 'Webhook Parser',
        system_prompt: 'You are a webhook parser',
        // No assistant_name
      };

      expect(isInlineAssistantCorrect(assistant)).toBe(true);
    });

    it('should correctly identify reference assistant without overrides', () => {
      const assistant: WorkflowAssistant = {
        id: 'checker',
        assistant_name: 'Checklist Generator Assistant',
      };

      expect(isInlineAssistantCorrect(assistant)).toBe(false);
    });

    it('should not treat assistant with only model as inline', () => {
      const assistant: WorkflowAssistant = {
        id: 'test',
        model: 'gpt-4',
        // No system_prompt, no assistant_name
      };

      // Not inline because missing system_prompt
      expect(isInlineAssistantCorrect(assistant)).toBe(false);
    });

    it('should not treat assistant with only system_prompt as inline', () => {
      const assistant: WorkflowAssistant = {
        id: 'test',
        system_prompt: 'You are helpful',
        // No model, no assistant_name
      };

      // Not inline because missing model
      expect(isInlineAssistantCorrect(assistant)).toBe(false);
    });

    it('should correctly handle reference with both model and system_prompt overrides', () => {
      const assistant: WorkflowAssistant = {
        id: 'test',
        assistant_name: 'Base Assistant',
        model: 'gpt-4',
        system_prompt: 'Override prompt',
      };

      // Still a reference because has assistant_name
      expect(isInlineAssistantCorrect(assistant)).toBe(false);
    });
  });

  describe('Real world scenario from codemie.yaml', () => {
    it('should handle the actual failing case', () => {
      // From workflows/test-cases-generation-workflow.yaml
      const assistants: WorkflowAssistant[] = [
        {
          id: 'checklist_generator',
          assistant_name: 'COPY Checklist generator assistant_v2',
        },
        {
          id: 'jira_test_management_assistant',
          model: 'gpt-4.1',
          assistant_name: 'Jira Test Management Assistant', // <- This one fails!
        },
        {
          id: 'webhook_parser',
          model: 'gpt-4o-mini',
          name: 'Webhook Parser',
          system_prompt: 'You are a webhook payload parser...',
        },
      ];

      // Check which ones need resolution
      const needsResolution = assistants.map((a) => ({
        id: a.id,
        isInlineBuggy: isInlineAssistantBuggy(a),
        isInlineCorrect: isInlineAssistantCorrect(a),
        hasAssistantName: Boolean(a.assistant_name),
      }));

      // checklist_generator: has assistant_name, no model
      expect(needsResolution[0].isInlineBuggy).toBe(false); // Works by accident
      expect(needsResolution[0].isInlineCorrect).toBe(false); // Correct
      expect(needsResolution[0].hasAssistantName).toBe(true);

      // jira_test_management_assistant: has assistant_name AND model
      expect(needsResolution[1].isInlineBuggy).toBe(true); // BUG: skipped!
      expect(needsResolution[1].isInlineCorrect).toBe(false); // Correct: not inline
      expect(needsResolution[1].hasAssistantName).toBe(true);

      // webhook_parser: inline (model + system_prompt, no assistant_name)
      expect(needsResolution[2].isInlineBuggy).toBe(true); // Works correctly
      expect(needsResolution[2].isInlineCorrect).toBe(true); // Correct
      expect(needsResolution[2].hasAssistantName).toBe(false);
    });
  });

  describe('deployWorkflows - real world deployment scenarios', () => {
    let tempDir: string;
    let stateManager: StateManager;
    let originalCwd: string;

    beforeEach(() => {
      originalCwd = process.cwd();
      tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'workflow-test-'));
      const appConfig = {
        rootDir: tempDir,
        codemieConfig: 'codemie.yaml',
        codemieState: 'state.json',
        backupsDirectory: 'backups',
      };
      stateManager = new StateManager(appConfig);
    });

    afterEach(() => {
      // Always restore original directory first
      if (process.cwd() !== originalCwd) {
        process.chdir(originalCwd);
      }
      // Then cleanup temp dir
      if (fs.existsSync(tempDir)) {
        fs.rmSync(tempDir, { recursive: true, force: true });
      }
    });

    it('should deploy new workflow with assistant references', async () => {
      // Setup: create assistant in state
      const assistant: AssistantResource = {
        name: 'Test Assistant',
        prompt: 'test.md',
        model: 'gpt-4',
        description: 'Test',
      };
      stateManager.updateAssistantState('Test Assistant', 'ast-123', 'prompt-checksum', assistant);

      // Create workflow YAML file
      const workflowYaml = `
assistants:
  - id: test_assistant
    assistant_name: Test Assistant
states:
  - id: start
    assistant_id: test_assistant
    task: Test task
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, workflowYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Test Workflow',
              description: 'Test workflow',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn().mockResolvedValue({ id: 'wf-new-123' }),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      // Change to temp dir
      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.created).toBe(1);
        expect(mockClient.workflows.create).toHaveBeenCalled();

        // Verify state was saved
        const savedState = stateManager.getWorkflowState('Test Workflow');
        expect(savedState?.id).toBe('wf-new-123');
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should update existing workflow when YAML changes', async () => {
      // Setup state
      const assistant: AssistantResource = {
        name: 'Test Assistant',
        prompt: 'test.md',
        model: 'gpt-4',
        description: 'Test',
      };
      stateManager.updateAssistantState('Test Assistant', 'ast-123', 'prompt', assistant);
      const oldYaml = 'assistants:\n  - id: test\n    assistant_name: Test Assistant';
      stateManager.updateWorkflowState(
        'Test Workflow',
        'wf-existing',
        calculateChecksum(oldYaml),
        'old-config-checksum'
      );

      // Create updated workflow YAML
      const newYaml = `
assistants:
  - id: test
    assistant_name: Test Assistant
states:
  - id: new_state
    assistant_id: test
    task: Updated task
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, newYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Test Workflow',
              description: 'Test workflow',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          update: jest.fn().mockResolvedValue({ id: 'wf-existing' }),
          get: jest.fn().mockResolvedValue({ id: 'wf-existing', name: 'Test Workflow' }),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.updated).toBe(1);
        expect(mockClient.workflows.update).toHaveBeenCalledWith('wf-existing', expect.any(Object));
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should skip unchanged workflow', async () => {
      const assistant: AssistantResource = {
        name: 'Test Assistant',
        prompt: 'test.md',
        model: 'gpt-4',
        description: 'Test',
      };
      stateManager.updateAssistantState('Test Assistant', 'ast-123', 'prompt', assistant);

      const yamlContent = `
assistants:
  - id: test
    assistant_name: Test Assistant
states:
  - id: start
    assistant_id: test
    task: Task
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, yamlContent);

      const workflow = {
        name: 'Test Workflow',
        description: 'Test',
        definition: 'workflow.yaml',
        mode: 'Sequential' as const,
        shared: true,
      };

      // Store checksums
      stateManager.updateWorkflowState(
        workflow.name,
        'wf-123',
        calculateChecksum(yamlContent),
        calculateWorkflowConfigChecksum(workflow)
      );

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: { assistants: [], datasources: [], workflows: [workflow] },
      };

      const mockClient = {
        workflows: {
          update: jest.fn(),
          create: jest.fn(),
          get: jest.fn().mockResolvedValue({ id: 'wf-123', name: 'Test Workflow' }),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.unchanged).toBe(1);
        expect(mockClient.workflows.update).not.toHaveBeenCalled();
        expect(mockClient.workflows.create).not.toHaveBeenCalled();
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should resolve workflow definition relative to provided rootDir', async () => {
      const assistant: AssistantResource = {
        name: 'Test Assistant',
        prompt: 'test.md',
        model: 'gpt-4',
        description: 'Test',
      };
      stateManager.updateAssistantState('Test Assistant', 'ast-rootdir', 'prompt', assistant);

      const workflowDir = path.join(tempDir, 'workflows');
      fs.mkdirSync(workflowDir, { recursive: true });
      const YAML_CONTENT = `
assistants:
  - id: referenced
    assistant_name: Test Assistant
states:
  - id: start
    assistant_id: referenced
    task: Root dir test
`;
      fs.writeFileSync(path.join(workflowDir, 'root-test.yaml'), YAML_CONTENT);

      const config: Partial<CodemieConfig> = {
        project: { name: 'RootDir Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'RootDir Workflow',
              description: 'Ensures rootDir is respected',
              definition: 'workflows/root-test.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn().mockResolvedValue({ id: 'wf-rootdir' }),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager, tempDir);

      expect(stats.created).toBe(1);
      expect(mockClient.workflows.create).toHaveBeenCalledWith(
        expect.objectContaining({
          project: 'RootDir Project',
          name: 'RootDir Workflow',
        })
      );
    });

    it('should handle workflow with inline and reference assistants', async () => {
      const refAssistant: AssistantResource = {
        name: 'Referenced Assistant',
        prompt: 'ref.md',
        model: 'gpt-4',
        description: 'Ref',
      };
      stateManager.updateAssistantState('Referenced Assistant', 'ast-ref', 'prompt', refAssistant);

      const workflowYaml = `
assistants:
  - id: ref_assistant
    assistant_name: Referenced Assistant
  - id: inline_assistant
    model: gpt-4
    name: Inline Assistant
    system_prompt: You are inline
states:
  - id: step1
    assistant_id: ref_assistant
    task: Use reference
  - id: step2
    assistant_id: inline_assistant
    task: Use inline
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, workflowYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Mixed Workflow',
              description: 'Has both types',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn().mockResolvedValue({ id: 'wf-mixed' }),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.created).toBe(1);

        // Verify the YAML was modified correctly
        const mockCalls = (mockClient.workflows.create as jest.Mock).mock.calls as Array<
          Array<{ yaml_config: string }>
        >;
        const yamlConfig = mockCalls[0]?.[0]?.yaml_config;

        // Should have resolved reference
        expect(yamlConfig).toContain('assistant_id: ast-ref');
        // Should NOT contain assistant_name anymore
        expect(yamlConfig).not.toContain('assistant_name');
        // Should keep inline assistant unchanged
        expect(yamlConfig).toContain('inline_assistant');
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should handle reference with model override', async () => {
      const baseAssistant: AssistantResource = {
        name: 'Base Assistant',
        prompt: 'base.md',
        model: 'gpt-4',
        description: 'Base',
      };
      stateManager.updateAssistantState('Base Assistant', 'ast-base', 'prompt', baseAssistant);

      const workflowYaml = `
assistants:
  - id: customized
    assistant_name: Base Assistant
    model: gpt-4-turbo
states:
  - id: start
    assistant_id: customized
    task: Use customized version
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, workflowYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Override Workflow',
              description: 'Uses model override',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn().mockResolvedValue({ id: 'wf-override' }),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.created).toBe(1);

        const mockCalls = (mockClient.workflows.create as jest.Mock).mock.calls as Array<
          Array<{ yaml_config: string }>
        >;
        const yamlConfig = mockCalls[0]?.[0]?.yaml_config;

        // Should resolve to assistant_id
        expect(yamlConfig).toContain('assistant_id: ast-base');
        // Should keep model override
        expect(yamlConfig).toContain('model: gpt-4-turbo');
        // Should remove assistant_name
        expect(yamlConfig).not.toContain('assistant_name');
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should throw error when assistant reference not found', async () => {
      const workflowYaml = `
assistants:
  - id: missing
    assistant_name: Non Existent Assistant
states:
  - id: start
    assistant_id: missing
    task: This will fail
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, workflowYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Broken Workflow',
              description: 'References missing assistant',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn(),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        // Should catch error and increment failed
        expect(stats.failed).toBe(1);
        expect(stats.created).toBe(0);
        expect(mockClient.workflows.create).not.toHaveBeenCalled();
      } finally {
        process.chdir(originalCwd);
      }
    });

    it('should resolve assistant from imported resources', async () => {
      const workflowYaml = `
assistants:
  - id: imported
    assistant_name: Imported Assistant
states:
  - id: start
    assistant_id: imported
    task: Use imported
`;
      const yamlPath = path.join(tempDir, 'workflow.yaml');
      fs.writeFileSync(yamlPath, workflowYaml);

      const config: Partial<CodemieConfig> = {
        project: { name: 'Test Project', description: 'Test' },
        imported: {
          assistants: [{ id: 'ast-imported', name: 'Imported Assistant' }],
          datasources: [],
          integrations: [],
        },
        resources: {
          assistants: [],
          datasources: [],
          workflows: [
            {
              name: 'Imported Workflow',
              description: 'Uses imported assistant',
              definition: 'workflow.yaml',
              mode: 'Sequential',
              shared: true,
            },
          ],
        },
      };

      const mockClient = {
        workflows: {
          create: jest.fn().mockResolvedValue({ id: 'wf-imported' }),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const originalCwd = process.cwd();
      process.chdir(tempDir);

      try {
        const stats = await deployWorkflows(config as CodemieConfig, mockClient, stateManager);

        expect(stats.created).toBe(1);

        const mockCalls = (mockClient.workflows.create as jest.Mock).mock.calls as Array<
          Array<{ yaml_config: string }>
        >;
        expect(mockCalls[0]?.[0]?.yaml_config).toContain('ast-imported');
      } finally {
        process.chdir(originalCwd);
      }
    });
  });
});

describe('deployWorkflows', () => {
  let tempDir: string;
  let stateManager: StateManager;

  const INLINE_YAML = `
assistants:
  - id: inline_one
    model: gpt-4
    system_prompt: You are inline
states:
  - id: start
    assistant_id: inline_one
    task: Do it
`;

  function workflowConfig(names: string[]): CodemieConfig {
    return {
      ...baseConfig(),
      resources: {
        assistants: [],
        datasources: [],
        workflows: names.map((name) => ({
          name,
          description: `${name} description`,
          definition: 'workflow.yaml',
        })),
      },
    };
  }

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'deploy-workflows-'));
    fs.writeFileSync(path.join(tempDir, 'workflow.yaml'), INLINE_YAML);
    stateManager = new StateManager({
      rootDir: tempDir,
      codemieConfig: 'codemie.yaml',
      codemieState: 'state.json',
      backupsDirectory: 'backups',
    });
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it('logs the SDK ApiError status and response when create fails', async () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    try {
      const apiError = Object.assign(new Error('Request failed'), { statusCode: 400, response: { detail: 'bad' } });
      const client = {
        workflows: {
          create: jest.fn().mockRejectedValue(apiError),
          get: jest.fn().mockRejectedValue(new Error('Not found')),
          list: jest.fn().mockResolvedValue([]),
        },
      } as unknown as CodeMieClient;

      const stats = await deployWorkflows(workflowConfig(['WF Broken']), client, stateManager, tempDir);

      expect(stats.failed).toBe(1);
      expect(errorSpy).toHaveBeenCalledWith('     Status: 400');
      expect(errorSpy).toHaveBeenCalledWith(`     Data: ${JSON.stringify({ detail: 'bad' }, null, 2)}`);
    } finally {
      errorSpy.mockRestore();
    }
  });

  function adoptClient(listed: Array<{ id: string; name: string }>): CodeMieClient {
    return {
      workflows: {
        create: jest.fn().mockResolvedValue({ id: 'wf-created' }),
        update: jest.fn().mockResolvedValue({}),
        get: jest.fn().mockRejectedValue(new Error('Not found')),
        list: jest.fn().mockResolvedValue(listed),
      },
    } as unknown as CodeMieClient;
  }

  it('adopts a same-name workflow in the project when the state id is stale', async () => {
    stateManager.updateWorkflowState('WF', 'wf-stale', 'old-yaml', 'old-config');
    const client = adoptClient([{ id: 'wf-found', name: 'WF' }]);

    const stats = await deployWorkflows(workflowConfig(['WF']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    expect(client.workflows.create).not.toHaveBeenCalled();
    expect(client.workflows.list).toHaveBeenCalledWith(expect.objectContaining({ projects: ['proj'] }));
    expect(client.workflows.update).toHaveBeenCalledWith(
      'wf-found',
      expect.objectContaining({ project: 'proj', name: 'WF', mode: 'Sequential', shared: true })
    );
    expect(stateManager.getWorkflowState('WF')?.id).toBe('wf-found');
  });

  it('adopts a same-name workflow when there is no state entry', async () => {
    const client = adoptClient([{ id: 'wf-found', name: 'WF' }]);

    const stats = await deployWorkflows(workflowConfig(['WF']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    expect(client.workflows.create).not.toHaveBeenCalled();
    expect(client.workflows.update).toHaveBeenCalledWith('wf-found', expect.anything());
    expect(stateManager.getWorkflowState('WF')?.id).toBe('wf-found');
  });

  it('creates the workflow when the state id is stale and no same-name workflow exists', async () => {
    stateManager.updateWorkflowState('WF', 'wf-stale', 'old-yaml', 'old-config');
    const client = adoptClient([{ id: 'wf-other', name: 'Other' }]);

    const stats = await deployWorkflows(workflowConfig(['WF']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 0 });
    expect(client.workflows.update).not.toHaveBeenCalled();
    expect(client.workflows.create).toHaveBeenCalledWith(
      expect.objectContaining({ project: 'proj', name: 'WF', mode: 'Sequential', shared: true })
    );
    expect(stateManager.getWorkflowState('WF')?.id).toBe('wf-created');
  });

  it('creates the workflow when there is no state entry and no same-name workflow exists', async () => {
    const client = adoptClient([]);

    const stats = await deployWorkflows(workflowConfig(['WF']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 0 });
    expect(client.workflows.create).toHaveBeenCalledTimes(1);
    expect(stateManager.getWorkflowState('WF')?.id).toBe('wf-created');
  });

  it('fails a workflow with duplicate same-name matches while still deploying the next one', async () => {
    const client = adoptClient([
      { id: 'b', name: 'Dup' },
      { id: 'a', name: 'Dup' },
    ]);

    const stats = await deployWorkflows(workflowConfig(['Dup', 'Fresh']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 1 });
    expect(client.workflows.update).not.toHaveBeenCalled();
    expect(client.workflows.create).toHaveBeenCalledTimes(1);
    expect(client.workflows.create).toHaveBeenCalledWith(expect.objectContaining({ name: 'Fresh' }));
    expect(stateManager.getWorkflowState('Dup')).toBeUndefined();
  });

  it('deploys a workflow YAML without an assistants section', async () => {
    fs.writeFileSync(
      path.join(tempDir, 'workflow.yaml'),
      `
states:
  - id: start
    task: Only inline states
`
    );
    const client = adoptClient([]);

    const stats = await deployWorkflows(workflowConfig(['WF']), client, stateManager, tempDir);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 0 });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// deployDatasources
// ─────────────────────────────────────────────────────────────────────────────

function buildDatasourceClient(
  opts: { getResolves?: boolean; createError?: Error | null; updateError?: Error | null; existingId?: string } = {}
): CodeMieClient {
  const existingId = opts.existingId ?? 'ds-existing-id';
  const datasources: Array<{ id: string; name?: string }> = [];

  return {
    datasources: {
      get: jest.fn(() =>
        opts.getResolves !== false
          ? Promise.resolve({ id: existingId, name: 'ds' })
          : Promise.reject(new Error('not found'))
      ),
      create: jest.fn(() => {
        if (opts.createError) {
          return Promise.reject(opts.createError);
        }
        datasources.push({ id: 'ds-new-id', name: 'ds' });
        return Promise.resolve({});
      }),
      update: jest.fn(() => {
        if (opts.updateError) {
          return Promise.reject(opts.updateError);
        }
        return Promise.resolve({});
      }),
      list: jest.fn(() => Promise.resolve(datasources)),
    },
  } as unknown as CodeMieClient;
}

function datasourceConfig(ds: Partial<DatasourceResource> & { name: string }): CodemieConfig {
  return {
    ...baseConfig(),
    resources: {
      assistants: [],
      datasources: [
        {
          type: 'knowledge_base_file',
          embeddings_model: 'amazon.titan-embed-text-v2:0',
          shared_with_project: true,
          description: 'test',
          ...ds,
        } as DatasourceResource,
      ],
      workflows: [],
    },
  };
}

describe('deployDatasources', () => {
  it('creates a new datasource when absent from state', async () => {
    const client = buildDatasourceClient({ getResolves: false });
    (client.datasources.list as jest.Mock).mockResolvedValue([{ id: 'ds-new-id', name: 'my-ds' }]);
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.created).toBe(1);
    expect(client.datasources.create).toHaveBeenCalledTimes(1);
    expect(state.getDatasourceState('my-ds')).toMatchObject({ id: 'ds-new-id' });
  });

  it('skips update when config unchanged', async () => {
    const client = buildDatasourceClient();
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });
    const ds = cfg.resources.datasources![0] as DatasourceResource;

    // Pre-populate state with matching checksum
    state.updateDatasourceState('my-ds', 'ds-existing-id', ds);

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.unchanged).toBe(1);
    expect(client.datasources.update).not.toHaveBeenCalled();
    expect(client.datasources.create).not.toHaveBeenCalled();
  });

  it('updates datasource when config has changed', async () => {
    const client = buildDatasourceClient();
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });
    const ds = cfg.resources.datasources![0] as DatasourceResource;

    // Pre-populate state with stale checksum
    state.updateDatasourceState('my-ds', 'ds-existing-id', { ...ds, description: 'old description' });

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.updated).toBe(1);
    expect(client.datasources.update).toHaveBeenCalledTimes(1);
  });

  it('treats 404 on update as read-only and marks unchanged', async () => {
    const notFoundError = new Error('Resource with unknown not found');
    const client = buildDatasourceClient({ updateError: notFoundError });
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });
    const ds = cfg.resources.datasources![0] as DatasourceResource;

    // Stale checksum so update is attempted
    state.updateDatasourceState('my-ds', 'ds-existing-id', { ...ds, description: 'old' });

    const stats = await deployDatasources(cfg, client, state);

    // Should NOT count as a failure
    expect(stats.failed).toBe(0);
    expect(stats.unchanged).toBe(1);
    // State checksum should be synced to current config
    const updatedState = state.getDatasourceState('my-ds');
    expect(updatedState?.id).toBe('ds-existing-id');
  });

  it('re-throws non-404 update errors', async () => {
    const networkError = new Error('ECONNRESET');
    const client = buildDatasourceClient({ updateError: networkError });
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });
    const ds = cfg.resources.datasources![0] as DatasourceResource;

    state.updateDatasourceState('my-ds', 'ds-existing-id', { ...ds, description: 'old' });

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.failed).toBe(1);
  });

  it('recovers existing ID when "already exists" error on create', async () => {
    const alreadyExistsError = new Error(
      'Index already exists. Please choose a different name for your index or use the existing index.'
    );
    const client = buildDatasourceClient({ getResolves: false, createError: alreadyExistsError });
    // findDatasourceByName uses list — return the existing datasource
    (client.datasources.list as jest.Mock).mockResolvedValue([{ id: 'ds-recovered-id', name: 'my-ds' }]);
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });

    const stats = await deployDatasources(cfg, client, state);

    // Should count as created (recovered), not failed
    expect(stats.failed).toBe(0);
    expect(stats.created).toBe(1);
    expect(state.getDatasourceState('my-ds')).toMatchObject({ id: 'ds-recovered-id' });
  });

  it('fails when "already exists" but datasource cannot be found by name', async () => {
    const alreadyExistsError = new Error('Index already exists.');
    const client = buildDatasourceClient({ getResolves: false, createError: alreadyExistsError });
    (client.datasources.list as jest.Mock).mockResolvedValue([]);
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.failed).toBe(1);
  });

  it('creates new datasource when state exists but not on platform', async () => {
    const client = buildDatasourceClient({ getResolves: false });
    (client.datasources.list as jest.Mock).mockResolvedValue([{ id: 'ds-new-id', name: 'my-ds' }]);
    const { state } = setupTempProject();
    const cfg = datasourceConfig({ name: 'my-ds' });
    const ds = cfg.resources.datasources![0] as DatasourceResource;

    // state has a stale ID that no longer exists on platform
    state.updateDatasourceState('my-ds', 'ds-gone-id', ds);

    const stats = await deployDatasources(cfg, client, state);

    expect(stats.created).toBe(1);
    expect(client.datasources.create).toHaveBeenCalledTimes(1);
    expect(state.getDatasourceState('my-ds')).toMatchObject({ id: 'ds-new-id' });
  });
});

describe('deploySkills', () => {
  const alreadyExists = (): Error => new Error('Skill already exists');

  function skillsConfig(names: string[]): CodemieConfig {
    const cfg = baseConfig();
    cfg.resources.skills = names.map((name) => ({ name, description: `${name} desc`, file: `${name}.skill.md` }));
    return cfg;
  }

  function writeSkillFiles(dir: string, names: string[]): void {
    for (const name of names) {
      fs.writeFileSync(path.join(dir, `${name}.skill.md`), `# ${name}`);
    }
  }

  function pagedSkills(pages: Array<Array<{ id: string; name: string }>>): jest.Mock {
    return jest.fn(({ page }: { page: number }) => Promise.resolve(pages[page] ?? []));
  }

  function filler(count: number, prefix: string): Array<{ id: string; name: string }> {
    return Array.from({ length: count }, (_, i) => ({ id: `${prefix}-${i}`, name: `${prefix}-${i}` }));
  }

  /** Writes a `<name>/SKILL.md` layout on disk (optionally with companion files) and returns its SkillResource. */
  function writeSkillMdSkill(dir: string, name: string, companions: Record<string, string> = {}): SkillResource {
    const skillDir = path.join(dir, name);
    fs.mkdirSync(skillDir, { recursive: true });
    fs.writeFileSync(path.join(skillDir, 'SKILL.md'), `# ${name}`);
    for (const [relPath, content] of Object.entries(companions)) {
      const abs = path.join(skillDir, relPath);
      fs.mkdirSync(path.dirname(abs), { recursive: true });
      fs.writeFileSync(abs, content);
    }
    return { name, description: `${name} desc`, file: `${name}/SKILL.md` };
  }

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('shares one name index across recoveries in a run so each page is listed once', async () => {
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Alpha', 'Beta']);
    const client = buildClient();
    (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
    (client.skills.update as jest.Mock).mockResolvedValue({});
    client.skills.list = pagedSkills([
      [...filler(99, 'p0'), { id: 'alpha-id', name: 'Alpha' }],
      [...filler(40, 'p1'), { id: 'beta-id', name: 'Beta' }],
    ]) as unknown as typeof client.skills.list;

    const stats = await deploySkills(skillsConfig(['Alpha', 'Beta']), client, loader, state);

    expect(stats).toEqual({ created: 0, updated: 2, unchanged: 0, failed: 0 });
    expect(client.skills.list).toHaveBeenCalledTimes(2);
    expect(client.skills.update).toHaveBeenCalledWith('alpha-id', expect.objectContaining({ name: 'Alpha' }));
    expect(client.skills.update).toHaveBeenCalledWith('beta-id', expect.objectContaining({ name: 'Beta' }));
    expect(state.getSkillState('Alpha')).toMatchObject({ id: 'alpha-id' });
    expect(state.getSkillState('Beta')).toMatchObject({ id: 'beta-id' });
  });

  it('builds a fresh name index for each run', async () => {
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Alpha']);
    const client = buildClient();
    (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
    (client.skills.update as jest.Mock).mockResolvedValue({});
    client.skills.list = pagedSkills([[{ id: 'alpha-id', name: 'Alpha' }]]) as unknown as typeof client.skills.list;

    await deploySkills(skillsConfig(['Alpha']), client, loader, state);
    const { state: freshState } = setupTempProject();
    await deploySkills(skillsConfig(['Alpha']), client, loader, freshState);

    expect(client.skills.list).toHaveBeenCalledTimes(2);
  });

  it('records the id of a skill created on the no-state and stale-state paths', async () => {
    const recordSpy = jest.spyOn(SkillNameIndex.prototype, 'record');
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Fresh', 'Stale']);
    state.updateSkillState('Stale', 'stale-old-id', 'old', {
      name: 'Stale',
      description: 'Stale desc',
      file: 'Stale.skill.md',
    });
    const client = buildClient();
    (client.skills.get as jest.Mock).mockRejectedValue(new Error('Not found'));
    (client.skills.create as jest.Mock).mockImplementation((params: { name: string }) =>
      Promise.resolve({ id: `${params.name.toLowerCase()}-new-id` })
    );

    const stats = await deploySkills(skillsConfig(['Fresh', 'Stale']), client, loader, state);

    expect(stats).toEqual({ created: 2, updated: 0, unchanged: 0, failed: 0 });
    expect(recordSpy).toHaveBeenCalledWith('Fresh', 'fresh-new-id');
    expect(recordSpy).toHaveBeenCalledWith('Stale', 'stale-new-id');
    expect(client.skills.list).not.toHaveBeenCalled();
  });

  it('fails the skill when an "already exists" name cannot be found and continues with the rest', async () => {
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Ghost', 'Real']);
    const client = buildClient();
    (client.skills.create as jest.Mock).mockImplementation((params: { name: string }) =>
      params.name === 'Ghost' ? Promise.reject(alreadyExists()) : Promise.resolve({ id: 'real-id' })
    );
    client.skills.list = pagedSkills([[{ id: 'other-id', name: 'Other' }]]) as unknown as typeof client.skills.list;

    const stats = await deploySkills(skillsConfig(['Ghost', 'Real']), client, loader, state);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 1 });
    expect(client.skills.update).not.toHaveBeenCalled();
    expect(state.getSkillState('Ghost')).toBeUndefined();
    expect(state.getSkillState('Real')).toMatchObject({ id: 'real-id' });
  });

  it('includes the config visibility in the update payload on the in-state update path', async () => {
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Vis1']);
    const client = buildClient();
    (client.skills.update as jest.Mock).mockResolvedValue({});

    const cfg = skillsConfig(['Vis1']);
    cfg.resources.skills![0].visibility = 'public';

    // Seed stale state so the change-detection marks this skill as updated, not unchanged.
    state.updateSkillState('Vis1', 'vis1-id', 'OLD CONTENT', {
      name: 'Vis1',
      description: 'stale desc',
      file: 'Vis1.skill.md',
    });

    await deploySkills(cfg, client, loader, state);

    expect(client.skills.update).toHaveBeenCalledWith('vis1-id', expect.objectContaining({ visibility: 'public' }));
  });

  it('includes the config visibility in the update payload on the recover-by-name path', async () => {
    const { dir, loader, state } = setupTempProject();
    writeSkillFiles(dir, ['Vis2']);
    const client = buildClient();
    (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
    (client.skills.update as jest.Mock).mockResolvedValue({});
    client.skills.list = pagedSkills([[{ id: 'vis2-id', name: 'Vis2' }]]) as unknown as typeof client.skills.list;

    const cfg = skillsConfig(['Vis2']);
    cfg.resources.skills![0].visibility = 'public';

    await deploySkills(cfg, client, loader, state);

    expect(client.skills.update).toHaveBeenCalledWith('vis2-id', expect.objectContaining({ visibility: 'public' }));
  });

  it('sends an inline-content skill body as content without reading any file from disk', async () => {
    // Deliberately do not call writeSkillFiles: if deploySkills fell back to loadSkillContent,
    // it would try to read a nonexistent file and throw.
    const { loader, state } = setupTempProject();
    const client = buildClient();
    (client.skills.create as jest.Mock).mockResolvedValue({ id: 'inline-id' });
    const cfg = baseConfig();
    cfg.resources.skills = [{ name: 'Inline', description: 'Inline desc', content: 'inline skill body' }];

    const stats = await deploySkills(cfg, client, loader, state);

    expect(stats).toEqual({ created: 1, updated: 0, unchanged: 0, failed: 0 });
    expect(client.skills.create).toHaveBeenCalledWith(expect.objectContaining({ content: 'inline skill body' }));
  });

  describe('companion files payload rule', () => {
    it('create payload omits companion_files when the skill has none', async () => {
      const { loader, state } = setupTempProject();
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'nc-id' });
      const cfg = baseConfig();
      cfg.resources.skills = [{ name: 'NoCompanion', description: 'NoCompanion desc', content: 'inline body' }];

      await deploySkills(cfg, client, loader, state);

      const createCall = (client.skills.create as jest.Mock).mock.calls[0][0];
      expect(createCall).not.toHaveProperty('companion_files');
    });

    it('create payload includes the full companion file list when the skill has files', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'CompNew', { 'notes.txt': 'hello', 'sub/data.json': '{"a":1}' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'compnew-id' });
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);

      const createCall = (client.skills.create as jest.Mock).mock.calls[0][0];
      expect(createCall.companion_files).toEqual([
        expect.objectContaining({ path: 'notes.txt', content: 'hello', encoding: 'text' }),
        expect.objectContaining({ path: 'sub/data.json', content: '{"a":1}', encoding: 'text' }),
      ]);
    });

    it('update payload omits companion_files when there are no files now and state records none', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['Plain']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      state.updateSkillState('Plain', 'plain-id', 'OLD CONTENT', {
        name: 'Plain',
        description: 'Plain desc',
        file: 'Plain.skill.md',
      });

      await deploySkills(skillsConfig(['Plain']), client, loader, state);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall).not.toHaveProperty('companion_files');
    });

    it('update payload includes the full companion file list when there are files now', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'CompUpd', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      state.updateSkillState('CompUpd', 'compupd-id', 'OLD CONTENT', {
        name: 'CompUpd',
        description: 'CompUpd desc',
        file: 'CompUpd/SKILL.md',
      });
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall.companion_files).toEqual([expect.objectContaining({ path: 'a.txt', content: 'A' })]);
    });

    it('update payload sends an empty companion_files array when state records files and the working tree now has none', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'CompClear', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'compclear-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      fs.rmSync(path.join(dir, 'CompClear', 'a.txt'));

      await deploySkills(cfg, client, loader, state, dir);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall.companion_files).toEqual([]);
    });

    it('update payload omits companion_files at the recover-by-name path when the skill has none', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['Recover1']);
      const client = buildClient();
      (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
      (client.skills.update as jest.Mock).mockResolvedValue({});
      client.skills.list = pagedSkills([
        [{ id: 'recover1-id', name: 'Recover1' }],
      ]) as unknown as typeof client.skills.list;

      await deploySkills(skillsConfig(['Recover1']), client, loader, state);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall).not.toHaveProperty('companion_files');
    });

    it('clears stale platform companion files at the recover-by-name path when the skill now has none', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['RecoverStale']);
      const client = buildClient();
      (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
      (client.skills.update as jest.Mock).mockResolvedValue({});
      (client.skills.listCompanionFiles as jest.Mock).mockResolvedValue([{ path: 'stale.txt' }]);
      client.skills.list = pagedSkills([
        [{ id: 'recoverstale-id', name: 'RecoverStale' }],
      ]) as unknown as typeof client.skills.list;

      await deploySkills(skillsConfig(['RecoverStale']), client, loader, state);

      expect(client.skills.listCompanionFiles).toHaveBeenCalledWith('recoverstale-id');
      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall.companion_files).toEqual([]);
    });

    it('omits companion_files at the recover-by-name path when the platform holds none either', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['RecoverClean']);
      const client = buildClient();
      (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
      (client.skills.update as jest.Mock).mockResolvedValue({});
      (client.skills.listCompanionFiles as jest.Mock).mockResolvedValue([]);
      client.skills.list = pagedSkills([
        [{ id: 'recoverclean-id', name: 'RecoverClean' }],
      ]) as unknown as typeof client.skills.list;

      await deploySkills(skillsConfig(['RecoverClean']), client, loader, state);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall).not.toHaveProperty('companion_files');
    });

    it('clears stale platform companion files when the state entry predates companion hashes', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['Legacy']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      (client.skills.listCompanionFiles as jest.Mock).mockResolvedValue([{ path: 'stale.txt' }]);
      // No companionFiles argument: exactly the shape a state entry written before companion
      // hashes existed has, so state cannot say what the platform holds.
      state.updateSkillState('Legacy', 'legacy-id', 'OLD CONTENT', {
        name: 'Legacy',
        description: 'Legacy desc',
        file: 'Legacy.skill.md',
      });

      await deploySkills(skillsConfig(['Legacy']), client, loader, state);

      expect(client.skills.listCompanionFiles).toHaveBeenCalledWith('legacy-id');
      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall.companion_files).toEqual([]);
    });

    it('leaves platform companion files untouched when the companion lookup fails', async () => {
      const warnSpy = jest.spyOn(logger, 'warn').mockImplementation();
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['LookupFail']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      (client.skills.listCompanionFiles as jest.Mock).mockRejectedValue(new Error('500 Internal Server Error'));
      state.updateSkillState('LookupFail', 'lookupfail-id', 'OLD CONTENT', {
        name: 'LookupFail',
        description: 'LookupFail desc',
        file: 'LookupFail.skill.md',
      });

      const stats = await deploySkills(skillsConfig(['LookupFail']), client, loader, state);

      // A platform that cannot answer (or has no companion-files endpoint at all) must not fail
      // the skill: the update goes through without the field, leaving the platform's files alone.
      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall).not.toHaveProperty('companion_files');
      const warnings = warnSpy.mock.calls.map((call) => String(call[0])).join('\n');
      expect(warnings).toContain('LookupFail');
      expect(warnings).toContain('500 Internal Server Error');
    });

    it('leaves platform companion files untouched when the companion lookup times out', async () => {
      jest.useFakeTimers();
      try {
        const warnSpy = jest.spyOn(logger, 'warn').mockImplementation();
        const { dir, loader, state } = setupTempProject();
        writeSkillFiles(dir, ['LookupHang']);
        const client = buildClient();
        (client.skills.update as jest.Mock).mockResolvedValue({});
        (client.skills.listCompanionFiles as jest.Mock).mockReturnValue(new Promise(() => {}));
        state.updateSkillState('LookupHang', 'lookuphang-id', 'OLD CONTENT', {
          name: 'LookupHang',
          description: 'LookupHang desc',
          file: 'LookupHang.skill.md',
        });

        const deployment = deploySkills(skillsConfig(['LookupHang']), client, loader, state);
        await jest.advanceTimersByTimeAsync(TIMEOUTS_MS.SKILL_FETCH);
        const stats = await deployment;

        expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
        const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
        expect(updateCall).not.toHaveProperty('companion_files');
        const warnings = warnSpy.mock.calls.map((call) => String(call[0])).join('\n');
        expect(warnings).toContain('LookupHang');
        expect(warnings.toLowerCase()).toContain('timeout');
      } finally {
        jest.useRealTimers();
      }
    });

    it('does not ask the platform when state already records that there are no companion files', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'KnownEmpty');
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'knownempty-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      fs.writeFileSync(path.join(dir, 'KnownEmpty', 'SKILL.md'), '# KnownEmpty changed');
      await deploySkills(cfg, client, loader, state, dir);

      expect(client.skills.listCompanionFiles).not.toHaveBeenCalled();
      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall).not.toHaveProperty('companion_files');
    });

    it('update payload includes the full companion file list at the recover-by-name path when the skill has files', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'Recover2', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockRejectedValue(alreadyExists());
      (client.skills.update as jest.Mock).mockResolvedValue({});
      client.skills.list = pagedSkills([
        [{ id: 'recover2-id', name: 'Recover2' }],
      ]) as unknown as typeof client.skills.list;
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);

      const updateCall = (client.skills.update as jest.Mock).mock.calls[0][1];
      expect(updateCall.companion_files).toEqual([expect.objectContaining({ path: 'a.txt', content: 'A' })]);
    });
  });

  describe('three-way change detection', () => {
    it('reports a content-only change as an update', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['ContentOnly']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      state.updateSkillState('ContentOnly', 'co-id', 'OLD CONTENT', {
        name: 'ContentOnly',
        description: 'ContentOnly desc',
        file: 'ContentOnly.skill.md',
      });

      const stats = await deploySkills(skillsConfig(['ContentOnly']), client, loader, state);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    });

    it('reports a config-only change as an update', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['ConfigOnly']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = skillsConfig(['ConfigOnly']);
      cfg.resources.skills![0].categories = ['newcat'];
      const content = fs.readFileSync(path.join(dir, 'ConfigOnly.skill.md'), 'utf8');
      state.updateSkillState('ConfigOnly', 'cfg-id', content, {
        name: 'ConfigOnly',
        description: 'ConfigOnly desc',
        file: 'ConfigOnly.skill.md',
      });

      const stats = await deploySkills(cfg, client, loader, state);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    });

    it('reports an added companion file as an update', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'AddComp');
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'addcomp-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      fs.writeFileSync(path.join(dir, 'AddComp', 'new.txt'), 'new content');

      const stats = await deploySkills(cfg, client, loader, state, dir);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    });

    it('reports a removed companion file as an update', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'RemoveComp', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'removecomp-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      fs.rmSync(path.join(dir, 'RemoveComp', 'a.txt'));

      const stats = await deploySkills(cfg, client, loader, state, dir);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    });

    it('reports an edited companion file as an update', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'EditComp', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'editcomp-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      fs.writeFileSync(path.join(dir, 'EditComp', 'a.txt'), 'A-edited');

      const stats = await deploySkills(cfg, client, loader, state, dir);

      expect(stats).toEqual({ created: 0, updated: 1, unchanged: 0, failed: 0 });
    });

    it('reports no change for an untouched skill', async () => {
      const { dir, loader, state } = setupTempProject();
      const skill = writeSkillMdSkill(dir, 'Untouched', { 'a.txt': 'A' });
      const client = buildClient();
      (client.skills.create as jest.Mock).mockResolvedValue({ id: 'untouched-id' });
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const cfg = baseConfig();
      cfg.resources.skills = [skill];

      await deploySkills(cfg, client, loader, state, dir);
      const stats = await deploySkills(cfg, client, loader, state, dir);

      expect(stats).toEqual({ created: 0, updated: 0, unchanged: 1, failed: 0 });
      expect(client.skills.update).not.toHaveBeenCalled();
    });

    it('treats a state entry missing both companion fields as no companion files', async () => {
      const { dir, loader, state } = setupTempProject();
      writeSkillFiles(dir, ['Legacy']);
      const client = buildClient();
      (client.skills.update as jest.Mock).mockResolvedValue({});
      const content = fs.readFileSync(path.join(dir, 'Legacy.skill.md'), 'utf8');
      state.updateSkillState('Legacy', 'legacy-id', content, {
        name: 'Legacy',
        description: 'Legacy desc',
        file: 'Legacy.skill.md',
      });

      const stats = await deploySkills(skillsConfig(['Legacy']), client, loader, state);

      expect(stats).toEqual({ created: 0, updated: 0, unchanged: 1, failed: 0 });
      expect(client.skills.update).not.toHaveBeenCalled();
    });
  });
});

describe('deploy --replace-skill-group', () => {
  const GROUP = 'bundle';
  let dir: string;
  let originalCwd: string;
  let client: CodeMieClient;
  let calls: string[];
  let attached: Record<string, string[]>;
  let cleanup: { findOrphanedResources: jest.Mock; deleteOrphanedResources: jest.Mock };
  let appConfig: { rootDir: string; codemieConfig: string; codemieState: string; backupsDirectory: string };

  function skillEntry(name: string, group?: string): SkillResource {
    return {
      name,
      description: `${name} description long enough`,
      file: `${name}.skill.md`,
      ...(group ? { group } : {}),
    };
  }

  /** Config: two grouped skills, one ungrouped, one assistant per skill kind, a datasource and a workflow. */
  function writeProject(): void {
    const cfg = baseConfig();
    cfg.resources.skills = [skillEntry('alpha', GROUP), skillEntry('beta', GROUP), skillEntry('gamma')];
    cfg.resources.assistants = [
      {
        name: 'Bundled',
        description: 'references the group',
        prompt: 'system_prompts/bundled.md',
        model: 'gpt-4',
        skills: ['alpha', 'gamma'],
      } as AssistantResource,
      {
        name: 'Untouched',
        description: 'references nothing from the group',
        prompt: 'system_prompts/untouched.md',
        model: 'gpt-4',
        skills: ['gamma'],
      } as AssistantResource,
    ];
    cfg.resources.datasources = [
      {
        name: 'cfg-ds',
        type: 'knowledge_base_file',
        embeddings_model: 'amazon.titan-embed-text-v2:0',
        shared_with_project: true,
        description: 'config datasource',
      } as DatasourceResource,
    ];
    cfg.resources.workflows = [{ name: 'cfg-wf', description: 'config workflow', definition: 'workflow.yaml' }];
    cfg.imported = {
      assistants: [{ name: 'Imported Assistant', id: 'ast-imported' }],
      datasources: [],
      skills: [],
      integrations: [],
    };
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));

    for (const name of ['alpha', 'beta', 'gamma']) {
      fs.writeFileSync(path.join(dir, `${name}.skill.md`), `# ${name}`);
    }
    fs.writeFileSync(path.join(dir, 'system_prompts/bundled.md'), 'BUNDLED_PROMPT');
    fs.writeFileSync(path.join(dir, 'system_prompts/untouched.md'), 'UNTOUCHED_PROMPT');
    fs.writeFileSync(path.join(dir, 'workflow.yaml'), 'states:\n  - id: start\n    task: Do it\n');
  }

  function seedState(): StateManager {
    const stateManager = new StateManager(appConfig);
    stateManager.updateSkillState('alpha', 'alpha-old-id', '# alpha', skillEntry('alpha', GROUP));
    stateManager.updateSkillState('beta', 'beta-old-id', '# beta', skillEntry('beta', GROUP));
    stateManager.updateSkillState('gamma', 'gamma-id', '# gamma', skillEntry('gamma'));
    stateManager.updateAssistantState('Bundled', 'ast-bundled', 'BUNDLED_PROMPT', {
      name: 'Bundled',
      prompt: 'system_prompts/bundled.md',
      model: 'gpt-4',
    } as AssistantResource);
    stateManager.updateAssistantState('Untouched', 'ast-untouched', 'UNTOUCHED_PROMPT', {
      name: 'Untouched',
      prompt: 'system_prompts/untouched.md',
      model: 'gpt-4',
    } as AssistantResource);
    stateManager.updateWorkflowState('cfg-wf', 'wf-id', 'yaml', 'config');
    return stateManager;
  }

  function buildReplaceClient(failingDeleteId?: string): CodeMieClient {
    const existingSkillIds = new Set(['alpha-old-id', 'beta-old-id', 'gamma-id']);
    return {
      assistants: {
        get: jest.fn((id: string) => Promise.resolve({ id, name: 'assistant' })),
        getBySlug: jest.fn().mockResolvedValue(null),
        list: jest.fn().mockResolvedValue([]),
        create: jest.fn(),
        update: jest.fn((id: string) => {
          calls.push(`assistant-update:${id}`);
          return Promise.resolve({});
        }),
      },
      datasources: {
        get: jest.fn().mockRejectedValue(new Error('not found')),
        list: jest.fn().mockResolvedValue([]),
        create: jest.fn().mockResolvedValue({}),
        update: jest.fn().mockResolvedValue({}),
        delete: jest.fn().mockResolvedValue({}),
      },
      workflows: {
        get: jest.fn((id: string) => Promise.resolve({ id })),
        list: jest.fn().mockResolvedValue([]),
        create: jest.fn().mockResolvedValue({ id: 'wf-new' }),
        update: jest.fn().mockResolvedValue({}),
        delete: jest.fn().mockResolvedValue({}),
      },
      skills: {
        get: jest.fn((id: string) =>
          existingSkillIds.has(id) ? Promise.resolve({ id }) : Promise.reject(new Error('not found'))
        ),
        list: jest.fn().mockResolvedValue([]),
        create: jest.fn((params: { name: string }) => {
          calls.push(`create:${params.name}`);
          const id = `${params.name}-new-id`;
          existingSkillIds.add(id);
          return Promise.resolve({ id });
        }),
        update: jest.fn().mockResolvedValue({}),
        delete: jest.fn((id: string) => {
          calls.push(`delete:${id}`);
          if (id === failingDeleteId) {
            return Promise.reject(new Error('platform refused to delete'));
          }
          existingSkillIds.delete(id);
          return Promise.resolve({});
        }),
        getAssistantSkills: jest.fn((assistantId: string) => {
          calls.push(`list-attached:${assistantId}`);
          return Promise.resolve((attached[assistantId] ?? []).map((id) => ({ id })));
        }),
        detachFromAssistant: jest.fn((assistantId: string, skillId: string) => {
          calls.push(`detach:${assistantId}:${skillId}`);
          attached[assistantId] = (attached[assistantId] ?? []).filter((id) => id !== skillId);
          return Promise.resolve({});
        }),
        attachToAssistant: jest.fn((assistantId: string, skillId: string) => {
          calls.push(`attach:${assistantId}:${skillId}`);
          attached[assistantId] = [...(attached[assistantId] ?? []), skillId];
          return Promise.resolve({});
        }),
      },
    } as unknown as CodeMieClient;
  }

  beforeEach(() => {
    originalCwd = process.cwd();
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'replace-group-test-'));
    fs.mkdirSync(path.join(dir, 'system_prompts'), { recursive: true });
    jest.clearAllMocks();
    jest.spyOn(console, 'log').mockImplementation();
    jest.spyOn(console, 'error').mockImplementation();

    appConfig = {
      rootDir: dir,
      codemieConfig: 'codemie.yaml',
      codemieState: 'state.json',
      backupsDirectory: 'backups',
    };
    writeProject();
    seedState();

    calls = [];
    attached = {
      'ast-bundled': ['alpha-old-id', 'beta-old-id', 'gamma-id'],
      'ast-untouched': ['gamma-id'],
      'ast-imported': ['beta-old-id'],
    };
    client = buildReplaceClient();
    mockCreateClient.mockResolvedValue(client);

    cleanup = {
      findOrphanedResources: jest.fn().mockReturnValue({ assistants: [], datasources: [], workflows: [], skills: [] }),
      deleteOrphanedResources: jest
        .fn()
        .mockResolvedValue({ deleted: { assistants: [], datasources: [], workflows: [], skills: [] }, errors: [] }),
    };
    MockedCleanupManager.mockImplementation(() => cleanup as unknown as CleanupManager);
  });

  afterEach(() => {
    if (process.cwd() !== originalCwd) {
      process.chdir(originalCwd);
    }
    jest.restoreAllMocks();
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  function readSkillState(): Record<string, { id: string; group?: string }> {
    const raw = JSON.parse(fs.readFileSync(path.join(dir, 'state.json'), 'utf8')) as {
      resources: { skills: Record<string, { id: string; group?: string }> };
    };
    return raw.resources.skills;
  }

  it('touches nothing without --yes-replace-skills', async () => {
    await expect(deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP })).rejects.toThrow(
      '--yes-replace-skills'
    );

    expect(mockCreateClient).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
    expect(readSkillState().alpha.id).toBe('alpha-old-id');
  });

  it('detaches every selected skill from state-managed and imported assistants before deleting it', async () => {
    await deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true });

    const detaches = calls.filter((call) => call.startsWith('detach:'));
    expect(detaches).toEqual(
      expect.arrayContaining([
        'detach:ast-bundled:alpha-old-id',
        'detach:ast-bundled:beta-old-id',
        'detach:ast-imported:beta-old-id',
      ])
    );
    expect(detaches).not.toContain('detach:ast-bundled:gamma-id');

    const firstDelete = calls.findIndex((call) => call.startsWith('delete:'));
    const lastDetach = calls.map((call) => call.startsWith('detach:')).lastIndexOf(true);
    expect(firstDelete).toBeGreaterThan(-1);
    expect(lastDetach).toBeLessThan(firstDelete);
    expect(calls).toContain('delete:alpha-old-id');
    expect(calls).toContain('delete:beta-old-id');
    expect(calls).not.toContain('delete:gamma-id');
  });

  it('aborts without recreating anything when a delete fails', async () => {
    client = buildReplaceClient('beta-old-id');
    mockCreateClient.mockResolvedValue(client);

    await expect(
      deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true })
    ).rejects.toThrow('platform refused to delete');

    expect(client.skills.create).not.toHaveBeenCalled();
    expect(calls.filter((call) => call.startsWith('create:'))).toEqual([]);
    expect(readSkillState().beta.id).toBe('beta-old-id');
  });

  it('recreates only the group skills and the assistants referencing them, leaving other types alone', async () => {
    await deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true });

    expect(calls.filter((call) => call.startsWith('create:')).sort()).toEqual(['create:alpha', 'create:beta']);
    expect(client.datasources.create).not.toHaveBeenCalled();
    expect(client.datasources.update).not.toHaveBeenCalled();
    expect(client.workflows.create).not.toHaveBeenCalled();
    expect(client.workflows.update).not.toHaveBeenCalled();
    expect(cleanup.findOrphanedResources).not.toHaveBeenCalled();
    expect(cleanup.deleteOrphanedResources).not.toHaveBeenCalled();
    expect(calls).toContain('assistant-update:ast-bundled');
    expect(calls).not.toContain('assistant-update:ast-untouched');

    const skills = readSkillState();
    expect(skills.alpha.id).toBe('alpha-new-id');
    expect(skills.beta.id).toBe('beta-new-id');
    expect(skills.alpha.group).toBe(GROUP);
    expect(skills.gamma.id).toBe('gamma-id');

    const raw = JSON.parse(fs.readFileSync(path.join(dir, 'state.json'), 'utf8')) as {
      resources: { workflows: Record<string, { id: string }> };
    };
    expect(raw.resources.workflows['cfg-wf'].id).toBe('wf-id');
  });

  it('reattaches the recreated skills to the referencing assistant', async () => {
    await deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true });

    expect(attached['ast-bundled'].sort()).toEqual(['alpha-new-id', 'gamma-id']);
  });

  it('resolves assistant datasource_names in replace mode while still skipping datasource deployment', async () => {
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'codemie.yaml'), 'utf8')) as CodemieConfig;
    cfg.resources.assistants![0].datasource_names = ['cfg-ds', 'imp-ds'];
    cfg.imported.datasources = [{ name: 'imp-ds', id: 'ds-imported' }];
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));

    await deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true });

    expect(calls).toContain('assistant-update:ast-bundled');
    expect(client.datasources.create).not.toHaveBeenCalled();
    expect(client.datasources.update).not.toHaveBeenCalled();
    expect(client.assistants.update).toHaveBeenCalledWith(
      'ast-bundled',
      expect.objectContaining({
        context: expect.arrayContaining([
          { context_type: 'knowledge_base', name: 'cfg-ds' },
          { context_type: 'knowledge_base', name: 'imp-ds' },
        ]),
      })
    );
  });

  it('refuses a group whose name collides with an imported skill', async () => {
    const cfg = JSON.parse(fs.readFileSync(path.join(dir, 'codemie.yaml'), 'utf8')) as CodemieConfig;
    cfg.imported.skills = [{ name: 'Bundle', id: 'skill-imported' }];
    fs.writeFileSync(path.join(dir, 'codemie.yaml'), JSON.stringify(cfg));

    await expect(
      deployModule.deployResources({ appConfig, replaceSkillGroup: GROUP, yesReplaceSkills: true })
    ).rejects.toThrow('matches an entry in imported.skills');

    expect(calls).toEqual([]);
  });

  it('refuses a group that matches no skill at all', async () => {
    await expect(
      deployModule.deployResources({ appConfig, replaceSkillGroup: 'nope', yesReplaceSkills: true })
    ).rejects.toThrow('Skill group "nope" matched no skills');

    expect(calls).toEqual([]);
  });
});
