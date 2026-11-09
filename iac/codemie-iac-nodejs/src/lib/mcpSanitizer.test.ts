/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import type { IaCMcpServer } from '../types/codemieConfig';

import { sanitizeMcpServer } from './mcpSanitizer';

describe('sanitizeMcpServer', () => {
  it('should drop top-level keys whose value is null or undefined', () => {
    const input = {
      name: 'playwright',
      command: null,
      arguments: undefined,
      config: null,
      tools_tokens_size_limit: null,
    } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out).toEqual({ name: 'playwright' });
    expect(out).not.toHaveProperty('command');
    expect(out).not.toHaveProperty('arguments');
    expect(out).not.toHaveProperty('config');
    expect(out).not.toHaveProperty('tools_tokens_size_limit');
  });

  it('should recurse into the config object', () => {
    const input = {
      name: 'figma',
      config: { command: 'npx', url: null, transport: undefined },
    } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out.config).toEqual({ command: 'npx' });
  });

  it('should recurse into nested config.env and config.headers at any depth', () => {
    const input = {
      name: 'nested',
      config: {
        command: 'npx',
        env: { TOKEN: 'abc', EMPTY: null },
        headers: { Authorization: 'Bearer x', Extra: null, deep: { a: 1, b: null } },
      },
    } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, Record<string, unknown>>;

    expect(out.config.env).toEqual({ TOKEN: 'abc' });
    expect(out.config.headers).toEqual({ Authorization: 'Bearer x', deep: { a: 1 } });
  });

  it('should return arrays by identity without inspecting their contents', () => {
    const args = ['-y', '@playwright/mcp@latest'];
    const tools = [{ name: 'browse', settings: null }];
    const input = { name: 'playwright', arguments: args, tools } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out.arguments).toBe(args);
    expect(out.tools).toBe(tools);
    expect((out.tools as Record<string, unknown>[])[0]).toHaveProperty('settings', null);
  });

  it('should drop an empty top-level mcp_connect_url', () => {
    const input = { name: 'figma', mcp_connect_url: '' } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out).not.toHaveProperty('mcp_connect_url');
  });

  it('should keep a non-empty mcp_connect_url', () => {
    const input = { name: 'figma', mcp_connect_url: 'https://mcp.figma.com' } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out.mcp_connect_url).toBe('https://mcp.figma.com');
  });

  it('should keep an empty config.url', () => {
    const input = { name: 'figma', config: { url: '' } } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out.config).toEqual({ url: '' });
  });

  it('should preserve falsy values that are not null or undefined', () => {
    const input = {
      name: 'falsy',
      enabled: false,
      tools_tokens_size_limit: 0,
      description: '',
    } as unknown as IaCMcpServer;

    const out = sanitizeMcpServer(input) as unknown as Record<string, unknown>;

    expect(out.enabled).toBe(false);
    expect(out.tools_tokens_size_limit).toBe(0);
    expect(out.description).toBe('');
  });

  it('should not mutate its input', () => {
    const input = {
      name: 'playwright',
      command: null,
      mcp_connect_url: '',
      config: { command: 'npx', url: null },
    } as unknown as IaCMcpServer;
    const clone = structuredClone(input);

    sanitizeMcpServer(input);

    expect(input).toEqual(clone);
  });

  it('should be idempotent', () => {
    const input = {
      name: 'playwright',
      command: null,
      mcp_connect_url: '',
      enabled: false,
      config: { command: 'npx', env: { A: null, B: 'b' } },
      arguments: ['-y'],
    } as unknown as IaCMcpServer;

    const once = sanitizeMcpServer(input);

    expect(sanitizeMcpServer(once)).toEqual(once);
  });

  it('should return a non-plain-object input unchanged instead of throwing', () => {
    // A hand-authored codemie.yaml can carry `mcp_servers: [null]` or a bare scalar entry,
    // and the checksum path reaches the sanitizer without any shape validation in between.
    expect(sanitizeMcpServer(null as unknown as IaCMcpServer)).toBeNull();
    expect(sanitizeMcpServer(undefined as unknown as IaCMcpServer)).toBeUndefined();
    expect(sanitizeMcpServer('figma' as unknown as IaCMcpServer)).toBe('figma');
    expect(sanitizeMcpServer(7 as unknown as IaCMcpServer)).toBe(7);
    expect(sanitizeMcpServer(false as unknown as IaCMcpServer)).toBe(false);
  });

  it('should return an array input unchanged by identity', () => {
    const input = [{ name: 'playwright' }] as unknown as IaCMcpServer;

    expect(sanitizeMcpServer(input)).toBe(input);
  });
});
