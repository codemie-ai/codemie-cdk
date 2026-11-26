/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import type { SkillDetail } from 'codemie-sdk';
import { SkillVisibility } from 'codemie-sdk';

import type { AssistantWithSkills } from './types/codemieConfig';

export function createMockAssistant(overrides: Partial<AssistantWithSkills> = {}): AssistantWithSkills {
  return {
    id: 'ast-123',
    name: 'Test Assistant',
    slug: 'test-assistant',
    description: 'A test assistant',
    system_prompt: '# Test Prompt\nYou are a test assistant.',
    system_prompt_history: [],
    llm_model_type: 'claude-4-6-sonnet',
    shared: true,
    is_react: false,
    is_global: false,
    assistant_ids: [],
    context: [],
    disabled_context_tools: [],
    conversation_starters: [],
    creator: 'user-1',
    mcp_servers: [],
    nested_assistants: [],
    project: 'test-project',
    skill_ids: [],
    toolkits: [],
    ...overrides,
  };
}

export function createMockSkill(overrides: Partial<SkillDetail> = {}): SkillDetail {
  return {
    id: 'sk-123',
    name: 'Test Skill',
    description: 'A test skill',
    content: '# Test Skill\nThis is a test skill.',
    project: 'test-project',
    visibility: SkillVisibility.PROJECT,
    created_by: { id: 'user-1', username: 'user-1', name: 'Test User' },
    categories: [],
    createdDate: '2025-01-01',
    updatedDate: null,
    is_attached: false,
    assistants_count: 0,
    user_abilities: [],
    unique_likes_count: 0,
    unique_dislikes_count: 0,
    toolkits: [],
    mcp_servers: [],
    ...overrides,
  };
}
