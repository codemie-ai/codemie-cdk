import type { CodeMieClient } from 'codemie-sdk';

import { CleanupManager } from './cleanupManager';
import type { StateManager } from './stateManager';

describe('orphan cleanup status handling', () => {
  it.each([404, 401])('handles HTTP %i using status rather than the message', async (statusCode) => {
    const state = {
      isManagedResource: jest.fn().mockReturnValue(true),
      getIdByName: jest.fn().mockReturnValue('old-id'),
      deleteDatasourceState: jest.fn(),
    };
    const client = {
      datasources: {
        delete: jest
          .fn()
          .mockRejectedValue(
            Object.assign(new Error(statusCode === 404 ? 'Unavailable' : 'Credentials not found'), { statusCode })
          ),
      },
    };
    const manager = new CleanupManager(client as unknown as CodeMieClient, state as unknown as StateManager);
    const result = await manager.deleteOrphanedResources({
      assistants: [],
      datasources: ['old-source'],
      workflows: [],
      skills: [],
    });
    if (statusCode === 404) {
      expect(result.errors).toHaveLength(0);
      expect(result.deleted.datasources).toEqual(['old-source']);
      expect(state.deleteDatasourceState).toHaveBeenCalledWith('old-source');
    } else {
      expect(result.errors).toHaveLength(1);
      expect(state.deleteDatasourceState).not.toHaveBeenCalled();
    }
  });
});
