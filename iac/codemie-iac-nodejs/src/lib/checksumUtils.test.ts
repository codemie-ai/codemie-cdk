/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import type { AssistantResource, IntegrationReference } from '../types/codemieConfig';

import { calculateChecksum, calculateAssistantConfigChecksum, DEFAULT_LLM_MODEL } from './checksumUtils';

// Helper to build a valid AssistantResource from partial input for tests
function buildAssistant(partial: Partial<AssistantResource> & { name: string }): AssistantResource {
  return {
    name: partial.name,
    description: partial.description ?? '',
    prompt: partial.prompt ?? 'dummy.prompt.md',
    model: partial.model ?? DEFAULT_LLM_MODEL,
    // Preserve explicitly provided optional fields
    shared: partial.shared,
    is_react: partial.is_react,
    hide_tool_outputs: partial.hide_tool_outputs,
    is_global: partial.is_global,
    icon_url: partial.icon_url,
    toolkits: partial.toolkits,
    context: partial.context,
    assistant_ids: partial.assistant_ids,
    conversation_starters: partial.conversation_starters,
    // Newly added fields to ensure checksum differences are captured
    temperature: partial.temperature,
    top_p: partial.top_p,
    mcp_servers: partial.mcp_servers,
    sub_assistants: partial.sub_assistants,
    skills: partial.skills,
  };
}

/**
 * Create a resolved integration object (as returned by ConfigLoader after $ref resolution).
 * Uses IntegrationReference type which accepts both $ref and full Integration objects.
 */
function createResolvedIntegration(alias: string): IntegrationReference {
  return {
    id: `integration-${alias.toLowerCase().replaceAll(' ', '-')}`,
    alias,
    credential_type: 'Jira', // Valid SDK CredentialTypesType value
    project_name: 'test-project',
    setting_type: 'project',
    credential_values: [],
  };
}

describe('checksumUtils', () => {
  describe('calculateChecksum', () => {
    it('should generate consistent SHA-256 checksums', () => {
      const content = 'test content';

      const checksum1 = calculateChecksum(content);
      const checksum2 = calculateChecksum(content);

      expect(checksum1).toBe(checksum2);
      expect(checksum1).toHaveLength(64); // SHA-256 produces 64 hex characters
    });

    it('should generate different checksums for different content', () => {
      const content1 = 'test content 1';
      const content2 = 'test content 2';

      const checksum1 = calculateChecksum(content1);
      const checksum2 = calculateChecksum(content2);

      expect(checksum1).not.toBe(checksum2);
    });

    it('should handle empty string', () => {
      const checksum = calculateChecksum('');

      expect(checksum).toHaveLength(64);
      expect(checksum).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    });

    it('should handle unicode characters', () => {
      const content = '你好世界 🌍';

      const checksum = calculateChecksum(content);

      expect(checksum).toHaveLength(64);
    });

    it('should throw TypeError for non-string input', () => {
      expect(() => calculateChecksum(123 as unknown as string)).toThrow(TypeError);
      expect(() => calculateChecksum(123 as unknown as string)).toThrow('expects string, got number');
    });

    it('should throw TypeError for null input', () => {
      expect(() => calculateChecksum(null as unknown as string)).toThrow(TypeError);
      expect(() => calculateChecksum(null as unknown as string)).toThrow('expects string, got object');
    });

    it('should throw TypeError for undefined input', () => {
      expect(() => calculateChecksum(undefined as unknown as string)).toThrow(TypeError);
      expect(() => calculateChecksum(undefined as unknown as string)).toThrow('expects string, got undefined');
    });

    it('should throw TypeError for object input', () => {
      expect(() => calculateChecksum({} as unknown as string)).toThrow(TypeError);
      expect(() => calculateChecksum({} as unknown as string)).toThrow('expects string, got object');
    });

    it('should throw TypeError for array input', () => {
      expect(() => calculateChecksum([] as unknown as string)).toThrow(TypeError);
      expect(() => calculateChecksum([] as unknown as string)).toThrow('expects string, got object');
    });

    it('should handle multiline content', () => {
      const content = 'Line 1\nLine 2\nLine 3';
      const checksum = calculateChecksum(content);

      expect(checksum).toHaveLength(64);
    });

    it('should produce different checksums for content with different whitespace', () => {
      const content1 = 'test content';
      const content2 = 'test  content';

      expect(calculateChecksum(content1)).not.toBe(calculateChecksum(content2));
    });
  });

  describe('calculateAssistantConfigChecksum', () => {
    it('should calculate checksum for minimal assistant config', () => {
      const assistant = buildAssistant({ name: 'Test Assistant' });

      const checksum = calculateAssistantConfigChecksum(assistant);

      expect(checksum).toHaveLength(64);
      expect(typeof checksum).toBe('string');
    });

    it('should calculate consistent checksums for same config', () => {
      const assistant = buildAssistant({ name: 'Test Assistant', description: 'Test description', model: 'gpt-4' });

      const checksum1 = calculateAssistantConfigChecksum(assistant);
      const checksum2 = calculateAssistantConfigChecksum(assistant);

      expect(checksum1).toBe(checksum2);
    });

    it('checksum is unchanged when hide_tool_outputs is absent or false', () => {
      const base = buildAssistant({ name: 'Test' });

      expect(calculateAssistantConfigChecksum({ ...base, hide_tool_outputs: false })).toBe(
        calculateAssistantConfigChecksum(base)
      );
    });

    it('checksum changes when hide_tool_outputs is true', () => {
      const base = buildAssistant({ name: 'Test' });

      expect(calculateAssistantConfigChecksum({ ...base, hide_tool_outputs: true })).not.toBe(
        calculateAssistantConfigChecksum(base)
      );
    });

    it('should default to gpt-4 when no model specified', () => {
      const assistant = buildAssistant({ name: 'Test' });

      const checksum = calculateAssistantConfigChecksum(assistant);

      expect(checksum).toHaveLength(64);
    });

    it('should handle all optional fields', () => {
      const assistant = buildAssistant({
        name: 'Full Assistant',
        description: 'Full description',
        model: 'gpt-4-turbo',
        temperature: 0.7,
        top_p: 0.9,
        shared: true,
        is_react: false,
        is_global: true,
        icon_url: 'https://example.com/icon.png',
        toolkits: [{ id: 'tk-1' }] as unknown as AssistantResource['toolkits'],
        context: [{ type: 'code', name: 'repo' }] as unknown as AssistantResource['context'],
        assistant_ids: ['ast-1', 'ast-2'],
        conversation_starters: ['Hello', 'Help me'],
        mcp_servers: [{ name: 'server1' }] as unknown as AssistantResource['mcp_servers'],
      });

      const checksum = calculateAssistantConfigChecksum(assistant);

      expect(checksum).toHaveLength(64);
    });

    it('should treat undefined fields as defaults', () => {
      const assistant1 = buildAssistant({
        name: 'Test',
        description: '',
        toolkits: [],
        context: [],
        mcp_servers: [],
        assistant_ids: [],
        conversation_starters: [],
        sub_assistants: [],
        skills: [],
      });
      const assistant2 = buildAssistant({ name: 'Test' });

      const checksum1 = calculateAssistantConfigChecksum(assistant1);
      const checksum2 = calculateAssistantConfigChecksum(assistant2);

      expect(checksum1).toBe(checksum2);
    });

    it('should reflect changes in key configuration fields', () => {
      const base = buildAssistant({ name: 'Test' });
      const variantDescription = buildAssistant({ name: 'Test', description: 'Desc 1' });
      const variantModel = buildAssistant({ name: 'Test', model: 'gpt-3.5-turbo' });
      const variantTemperature = buildAssistant({ name: 'Test', temperature: 0.9 });
      const variantToolkits = buildAssistant({
        name: 'Test',
        toolkits: [{ id: 'tk-x' }] as unknown as AssistantResource['toolkits'],
      });

      const baseChecksum = calculateAssistantConfigChecksum(base);
      expect(calculateAssistantConfigChecksum(variantDescription)).not.toBe(baseChecksum);
      expect(calculateAssistantConfigChecksum(variantModel)).not.toBe(baseChecksum);
      expect(calculateAssistantConfigChecksum(variantTemperature)).not.toBe(baseChecksum);
      expect(calculateAssistantConfigChecksum(variantToolkits)).not.toBe(baseChecksum);
    });

    it('should reflect changes in skills', () => {
      const base = buildAssistant({ name: 'Test' });
      const variantSkills = buildAssistant({ name: 'Test', skills: ['skill-a'] });

      const baseChecksum = calculateAssistantConfigChecksum(base);
      expect(calculateAssistantConfigChecksum(variantSkills)).not.toBe(baseChecksum);
    });

    it('should include buildConfig in checksum when provided', () => {
      const assistant = buildAssistant({ name: 'Test' });
      const buildConfig1 = { version: '1.0' };
      const buildConfig2 = { version: '2.0' };

      const checksum1 = calculateAssistantConfigChecksum(assistant, buildConfig1);
      const checksum2 = calculateAssistantConfigChecksum(assistant, buildConfig2);
      const checksum3 = calculateAssistantConfigChecksum(assistant, null);

      expect(checksum1).not.toBe(checksum2);
      expect(checksum1).not.toBe(checksum3);
      expect(checksum2).not.toBe(checksum3);
    });

    it('should handle null buildConfig as default', () => {
      const assistant = buildAssistant({ name: 'Test' });

      const checksum1 = calculateAssistantConfigChecksum(assistant);
      const checksum2 = calculateAssistantConfigChecksum(assistant, null);

      expect(checksum1).toBe(checksum2);
    });

    describe('$ref vs resolved integration consistency', () => {
      // This tests the bug where backup generates config with $ref
      // but preview resolves $ref to full integration object
      // causing checksum mismatch

      it('should produce same checksum for $ref and resolved integration in toolkit settings', () => {
        // Config as saved in backup (with $ref)
        const assistantWithRef = buildAssistant({
          name: 'Test',
          toolkits: [
            {
              toolkit: 'Jira',
              label: 'Jira',
              settings_config: false,
              is_external: false,
              tools: [{ name: 'jira_tool', settings: { $ref: 'imported.integrations.Jira Connection' } }],
            },
          ],
        });

        // Config as loaded by ConfigLoader (with resolved $ref)
        const assistantWithResolved = buildAssistant({
          name: 'Test',
          toolkits: [
            {
              toolkit: 'Jira',
              label: 'Jira',
              settings_config: false,
              is_external: false,
              tools: [{ name: 'jira_tool', settings: createResolvedIntegration('Jira Connection') }],
            },
          ],
        });

        const checksumRef = calculateAssistantConfigChecksum(assistantWithRef);
        const checksumResolved = calculateAssistantConfigChecksum(assistantWithResolved);

        expect(checksumRef).toBe(checksumResolved);
      });

      it('should produce same checksum for $ref and resolved integration in mcp_servers', () => {
        // Config as saved in backup (with $ref)
        const assistantWithRef = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'gitlab-mcp', settings: { $ref: 'imported.integrations.GitLab Connection' } }],
        });

        // Config as loaded by ConfigLoader (with resolved $ref)
        const assistantWithResolved = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'gitlab-mcp', settings: createResolvedIntegration('GitLab Connection') }],
        });

        const checksumRef = calculateAssistantConfigChecksum(assistantWithRef);
        const checksumResolved = calculateAssistantConfigChecksum(assistantWithResolved);

        expect(checksumRef).toBe(checksumResolved);
      });

      it('should ignore null-valued mcp keys when comparing checksums', () => {
        const assistantWithNulls = buildAssistant({
          name: 'Test',
          mcp_servers: [
            {
              name: 'Figma',
              command: 'npx',
              arguments: '-y figma-developer-mcp --stdio',
              config: null,
              tools_tokens_size_limit: null,
              mcp_connect_url: '',
            },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        const assistantWithoutNulls = buildAssistant({
          name: 'Test',
          mcp_servers: [
            {
              name: 'Figma',
              command: 'npx',
              arguments: '-y figma-developer-mcp --stdio',
            },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(assistantWithNulls)).toBe(
          calculateAssistantConfigChecksum(assistantWithoutNulls)
        );
      });

      it('should ignore an empty mcp_connect_url versus an absent one', () => {
        const withEmptyUrl = buildAssistant({
          name: 'Test',
          mcp_servers: [
            { name: 'Figma', mcp_config_id: 'cfg-1', mcp_connect_url: '' },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        const withoutUrl = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'Figma', mcp_config_id: 'cfg-1' }] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(withEmptyUrl)).toBe(calculateAssistantConfigChecksum(withoutUrl));
      });

      it('should produce the same checksum regardless of mcp server key order', () => {
        const oneOrder = buildAssistant({
          name: 'Test',
          mcp_servers: [
            { name: 'Figma', command: 'npx', enabled: true, arguments: '-y figma-developer-mcp --stdio' },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        const otherOrder = buildAssistant({
          name: 'Test',
          mcp_servers: [
            { arguments: '-y figma-developer-mcp --stdio', enabled: true, name: 'Figma', command: 'npx' },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(oneOrder)).toBe(calculateAssistantConfigChecksum(otherOrder));
      });

      it('should produce the same checksum regardless of key order inside nested mcp objects', () => {
        const oneOrder = buildAssistant({
          name: 'Test',
          mcp_servers: [
            {
              name: 'Figma',
              config: { command: 'npx', env: { TOKEN: 'x', REGION: 'eu' }, headers: { a: '1', b: '2' } },
            },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        const otherOrder = buildAssistant({
          name: 'Test',
          mcp_servers: [
            {
              name: 'Figma',
              config: { headers: { b: '2', a: '1' }, env: { REGION: 'eu', TOKEN: 'x' }, command: 'npx' },
            },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(oneOrder)).toBe(calculateAssistantConfigChecksum(otherOrder));
      });

      it('should keep mcp array order significant', () => {
        const oneOrder = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'A' }, { name: 'B' }] as unknown as AssistantResource['mcp_servers'],
        });

        const reversed = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'B' }, { name: 'A' }] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(oneOrder)).not.toBe(calculateAssistantConfigChecksum(reversed));
      });

      it('should not throw on a null or primitive mcp_servers entry', () => {
        const withNullEntry = buildAssistant({
          name: 'Test',
          mcp_servers: [null, 'figma'] as unknown as AssistantResource['mcp_servers'],
        });

        expect(() => calculateAssistantConfigChecksum(withNullEntry)).not.toThrow();
      });

      it('should still produce a different checksum for a genuine mcp value change', () => {
        const original = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'Figma', command: 'npx' }] as unknown as AssistantResource['mcp_servers'],
        });

        const changed = buildAssistant({
          name: 'Test',
          mcp_servers: [{ name: 'Figma', command: 'uvx' }] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(original)).not.toBe(calculateAssistantConfigChecksum(changed));
      });

      it('should match the pinned checksum for a canonical MCP-bearing assistant', () => {
        // Golden hash: any unintended re-hash fails here instead of surfacing in an operator's plan.
        // Updated deliberately when MCP normalization started sorting keys (one-time drift, this release).
        const assistant = buildAssistant({
          name: 'Golden',
          description: 'Golden assistant',
          prompt: 'golden.prompt.md',
          mcp_servers: [
            {
              name: 'Figma',
              description: 'Figma MCP',
              enabled: true,
              command: 'npx',
              arguments: '-y figma-developer-mcp --stdio',
            },
          ] as unknown as AssistantResource['mcp_servers'],
        });

        expect(calculateAssistantConfigChecksum(assistant)).toBe(
          '2e1c23cd4dd9553b3d428f42d94af028fbe19ac68ead742dfa82b997657fde1b'
        );
      });

      it('should produce same checksum when toolkit has multiple tools with mixed settings', () => {
        // Config as saved in backup (with $ref)
        const assistantWithRef = buildAssistant({
          name: 'Test',
          toolkits: [
            {
              toolkit: 'Mixed Toolkit',
              label: 'Mixed Toolkit',
              settings_config: false,
              is_external: false,
              tools: [
                { name: 'tool_with_ref', settings: { $ref: 'imported.integrations.Integration A' } },
                { name: 'tool_without_settings', settings: null },
              ],
            },
          ],
        });

        // Config as loaded by ConfigLoader (with resolved $ref)
        const assistantWithResolved = buildAssistant({
          name: 'Test',
          toolkits: [
            {
              toolkit: 'Mixed Toolkit',
              label: 'Mixed Toolkit',
              settings_config: false,
              is_external: false,
              tools: [
                { name: 'tool_with_ref', settings: createResolvedIntegration('Integration A') },
                { name: 'tool_without_settings', settings: null },
              ],
            },
          ],
        });

        const checksumRef = calculateAssistantConfigChecksum(assistantWithRef);
        const checksumResolved = calculateAssistantConfigChecksum(assistantWithResolved);

        expect(checksumRef).toBe(checksumResolved);
      });
    });
  });
});
