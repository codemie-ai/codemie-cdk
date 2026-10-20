import type { AssistantCreateParams, CodeMieClient } from 'codemie-sdk';

import { AssistantValidationError, createAssistantAndGetId } from './assistantHelpers';

const params: AssistantCreateParams = {
  name: 'Example Assistant',
  description: 'Example assistant',
  project: 'example-project',
  system_prompt: 'Example',
  llm_model_type: 'gpt-4o',
  toolkits: [],
  context: [],
  conversation_starters: [],
  mcp_servers: [],
  assistant_ids: [],
  prompt_variables: [],
};

function services() {
  return { create: jest.fn(), getBySlug: jest.fn(), list: jest.fn() };
}

describe('assistant create result handling', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it.each(['assistant_id', 'assistantId', 'id'])('uses %s without lookup', async (key) => {
    const assistants = services();
    assistants.create.mockResolvedValue({ message: 'Saved', [key]: ' example-id ' });
    await expect(createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params)).resolves.toBe(
      'example-id'
    );
    expect(assistants.list).not.toHaveBeenCalled();
    expect(assistants.getBySlug).not.toHaveBeenCalled();
  });

  it('rejects validation before lookup, even if the response includes an ID', async () => {
    const assistants = services();
    const response = {
      assistantId: 'unsafe-id',
      validation: { has_missing_integrations: true, message: 'Configure integration' },
    };
    assistants.create.mockResolvedValue(response);
    await expect(createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params)).rejects.toMatchObject({
      name: 'AssistantValidationError',
      response,
      statusCode: 200,
    });
    expect(assistants.list).not.toHaveBeenCalled();
    expect(assistants.getBySlug).not.toHaveBeenCalled();
  });

  it('retries a genuinely missing ID until the index catches up', async () => {
    const assistants = services();
    assistants.create.mockResolvedValue({ message: 'Accepted' });
    assistants.list
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValue([{ name: params.name, id: 'visible-id' }]);
    const pending = createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params);
    const result = expect(pending).resolves.toBe('visible-id');
    await jest.runAllTimersAsync();
    await result;
    expect(assistants.create).toHaveBeenCalledTimes(1);
    expect(assistants.list).toHaveBeenCalledTimes(3);
  });

  it('retries slug 404s, but stops after six attempts', async () => {
    const assistants = services();
    assistants.create.mockResolvedValue({});
    assistants.getBySlug.mockRejectedValue(Object.assign(new Error('Unavailable'), { statusCode: 404 }));
    const pending = createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params, 'example');
    const result = expect(pending).rejects.toThrow('Assistant created but not found by slug: example');
    await jest.runAllTimersAsync();
    await result;
    expect(assistants.getBySlug).toHaveBeenCalledTimes(6);
    expect(assistants.create).toHaveBeenCalledTimes(1);
  });

  it('surfaces a non-404 lookup error immediately', async () => {
    const assistants = services();
    const error = Object.assign(new Error('Forbidden'), { statusCode: 403 });
    assistants.create.mockResolvedValue({});
    assistants.getBySlug.mockRejectedValue(error);
    await expect(createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params, 'example')).rejects.toBe(
      error
    );
    expect(assistants.getBySlug).toHaveBeenCalledTimes(1);
  });

  it('does not replace the original POST failure with a lookup failure', async () => {
    const assistants = services();
    const error = Object.assign(new Error('Validation rejected'), {
      statusCode: 422,
      response: { detail: 'Missing field' },
    });
    assistants.create.mockRejectedValue(error);
    await expect(createAssistantAndGetId({ assistants } as unknown as CodeMieClient, params)).rejects.toBe(error);
    expect(assistants.list).not.toHaveBeenCalled();
    expect(error).not.toBeInstanceOf(AssistantValidationError);
  });
});
