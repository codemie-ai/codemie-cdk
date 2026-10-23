/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */
import type { CodeMieClient, Assistant } from 'codemie-sdk';

import { createAssistantAndGetId } from './assistantHelpers';

describe('assistantHelpers', () => {
  jest.setTimeout(15_000);
  describe('createAssistantAndGetId', () => {
    test('should create assistant and retrieve ID by slug', async () => {
      const mockAssistant = {
        id: 'test-uuid-123',
        name: 'Test Assistant',
      } as Assistant;

      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn().mockResolvedValue(mockAssistant),
          list: jest.fn(),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
      };

      const id = await createAssistantAndGetId(mockClient, params, 'test-slug');

      expect(mockClient.assistants.create).toHaveBeenCalledWith(params);
      expect(mockClient.assistants.getBySlug).toHaveBeenCalledWith('test-slug');
      expect(id).toBe('test-uuid-123');
    });

    test('should create assistant and retrieve ID by name when no slug provided', async () => {
      const mockAssistants = [
        {
          id: 'uuid-123',
          name: 'Other Assistant',
        },
        {
          id: 'new-uuid-456',
          name: 'Test Assistant',
        },
      ] as Assistant[];

      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn(),
          list: jest.fn().mockResolvedValue(mockAssistants),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
      };

      const id = await createAssistantAndGetId(mockClient, params);

      expect(mockClient.assistants.create).toHaveBeenCalledWith(params);
      expect(mockClient.assistants.list).toHaveBeenCalledWith({ page: 0, per_page: 100 });
      expect(id).toBe('new-uuid-456');
    });

    test('should find global assistant via marketplace scope when is_global is true', async () => {
      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn(),
          list: jest.fn().mockImplementation((params: { scope?: string }) => {
            if (params.scope === 'marketplace') {
              return Promise.resolve([{ id: 'global-uuid-789', name: 'Test Assistant' }] as Assistant[]);
            }
            return Promise.resolve([] as Assistant[]);
          }),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
        is_global: true,
        shared: true,
      };

      const id = await createAssistantAndGetId(mockClient, params);

      expect(id).toBe('global-uuid-789');
      expect(mockClient.assistants.list).toHaveBeenCalledWith(expect.objectContaining({ scope: 'marketplace' }));
    });

    test('should not search marketplace scope when is_global is false', async () => {
      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn(),
          list: jest.fn().mockResolvedValue([] as Assistant[]),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
        is_global: false,
        shared: true,
      };

      await expect(createAssistantAndGetId(mockClient, params)).rejects.toThrow(
        'Assistant created but not found by name: Test Assistant'
      );
      expect(mockClient.assistants.list).not.toHaveBeenCalledWith(expect.objectContaining({ scope: 'marketplace' }));
    });

    test('should throw error when assistant not found by slug', async () => {
      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn().mockResolvedValue(null),
          list: jest.fn(),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
      };

      await expect(createAssistantAndGetId(mockClient, params, 'non-existent-slug')).rejects.toThrow(
        'Assistant created but not found by slug: non-existent-slug'
      );
    });

    test('should throw error when assistant not found by name', async () => {
      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn(),
          list: jest.fn().mockResolvedValue([]), // Empty list
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
      };

      await expect(createAssistantAndGetId(mockClient, params)).rejects.toThrow(
        'Assistant created but not found by name: Test Assistant'
      );
    });

    test('should find assistant with valid ID', async () => {
      const mockAssistants = [
        {
          id: 'valid-uuid',
          name: 'Test Assistant',
        } as Assistant,
        {
          id: 'other-uuid',
          name: 'Other Assistant',
        } as Assistant,
      ];

      const mockClient = {
        assistants: {
          create: jest.fn().mockResolvedValue(undefined),
          getBySlug: jest.fn(),
          list: jest.fn().mockResolvedValue(mockAssistants),
        },
      } as unknown as CodeMieClient;

      const params = {
        name: 'Test Assistant',
        system_prompt: 'Test prompt',
        project: 'test-project',
        llm_model_type: 'gpt-4o',
        description: 'Test',
        context: [],
        toolkits: [],
        conversation_starters: [],
        mcp_servers: [],
        assistant_ids: [],
        prompt_variables: [],
      };

      const id = await createAssistantAndGetId(mockClient, params);

      expect(mockClient.assistants.create).toHaveBeenCalledWith(params);
      expect(id).toBe('valid-uuid');
    });
  });
});
