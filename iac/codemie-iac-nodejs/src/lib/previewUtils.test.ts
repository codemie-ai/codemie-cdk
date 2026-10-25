/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { CodeMieClient } from 'codemie-sdk';

import type { AppConfig } from '../appConfig';
import type { AssistantResource, CodemieConfig } from '../types/codemieConfig';

import type { CodemieConfigLoader } from './codemieConfigLoader';
import { previewAssistants } from './previewUtils';
import { checkAssistantExists } from './resourceExistenceChecker';
import { StateManager } from './stateManager';

jest.mock('./resourceExistenceChecker', () => ({
  ...jest.requireActual('./resourceExistenceChecker'),
  checkAssistantExists: jest.fn(),
}));

describe('previewAssistants deselected_default_tools', () => {
  let tempDir: string;

  beforeEach(() => {
    (checkAssistantExists as jest.Mock).mockResolvedValue(true);
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codemie-preview-test-'));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  const base: AssistantResource = { name: 'A', description: 'd', prompt: 'p.md', model: 'gpt-4' };
  const loader = { loadPrompt: () => 'prompt', loadAssistantConfig: () => null } as unknown as CodemieConfigLoader;
  const client = {} as CodeMieClient;
  const config = {} as CodemieConfig;

  function makeState(): StateManager {
    const appConfig: AppConfig = {
      rootDir: tempDir,
      codemieConfig: 'codemie.yaml',
      codemieState: '.codemie/state.json',
      backupsDirectory: '.codemie/backups',
    };
    const sm = new StateManager(appConfig);
    sm.loadState();
    sm.updateAssistantState('A', 'id-1', 'prompt', base);
    return sm;
  }

  it('flags an update when only deselected_default_tools changed', async () => {
    const sm = makeState();
    const changed = { ...base, deselected_default_tools: ['search_kb'] };

    const [change] = await previewAssistants([changed], loader, sm, client, config);

    expect(change.type).toBe('update');
  });

  it('reports no-change when the list is unchanged', async () => {
    const sm = makeState();

    const [change] = await previewAssistants([base], loader, sm, client, config);

    expect(change.type).toBe('no-change');
  });
});
