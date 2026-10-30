/*
 * Copyright © 2025 EPAM Systems, Inc. All Rights Reserved. All information contained herein is, and remains the
 * property of EPAM Systems, Inc. and/or its suppliers and is protected by international intellectual
 * property law. Dissemination of this information or reproduction of this material is strictly forbidden,
 * unless prior written permission is obtained from EPAM Systems, Inc
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import {
  sanitizeFileName,
  generateMcpFileName,
  generateUniqueFileName,
  validateBackupDirectory,
  moveAtomically,
  cleanupDirectory,
  resolvePathWithinDirectory,
  skillDirRelativePath,
  skillFlatFileRelativePath,
  skillMarkdownRelativePath,
} from './fileUtils';

describe('sanitizeFileName', () => {
  it('should convert to lowercase and replace spaces with hyphens', () => {
    expect(sanitizeFileName('My Assistant Name')).toBe('my-assistant-name');
  });

  it('should remove special characters', () => {
    expect(sanitizeFileName('Name!@#$%^&*()')).toBe('name');
  });

  it('should handle multiple consecutive non-alphanumeric characters', () => {
    expect(sanitizeFileName('My   ---   Name')).toBe('my-name');
  });

  it('should trim leading and trailing dashes', () => {
    expect(sanitizeFileName('---name---')).toBe('name');
  });

  it('should prevent path traversal attacks', () => {
    expect(sanitizeFileName('../../../etc/passwd')).toBe('etc-passwd');
    expect(sanitizeFileName('..\\..\\windows\\system32')).toBe('windows-system32');
    expect(sanitizeFileName('/etc/shadow')).toBe('etc-shadow');
    expect(sanitizeFileName('C:\\Windows\\System32')).toBe('c-windows-system32');
  });

  it('should enforce length limit', () => {
    const longName = 'a'.repeat(300);
    expect(sanitizeFileName(longName).length).toBe(255);
  });

  it('should respect custom length limit', () => {
    const longName = 'a'.repeat(100);
    expect(sanitizeFileName(longName, 50).length).toBe(50);
  });

  it('should throw error if result is empty', () => {
    expect(() => sanitizeFileName('...')).toThrow('Sanitized filename is empty');
    expect(() => sanitizeFileName('///')).toThrow('Sanitized filename is empty');
    expect(() => sanitizeFileName('!!!')).toThrow('Sanitized filename is empty');
  });

  it('should handle names with only path separators', () => {
    expect(() => sanitizeFileName('../../../')).toThrow('Sanitized filename is empty');
  });
});

describe('generateMcpFileName', () => {
  it('should generate correct filename', () => {
    expect(generateMcpFileName('My Assistant', 'Playwright')).toBe('my-assistant_playwright.json');
  });

  it('should handle special characters in both names', () => {
    expect(generateMcpFileName('Git Server!', 'MCP-Tool')).toBe('git-server_mcp-tool.json');
  });

  it('should prevent path traversal in generated filenames', () => {
    expect(generateMcpFileName('../malicious', '../../attack')).toBe('malicious_attack.json');
  });
});

describe('generateUniqueFileName', () => {
  let tempDir: string;

  afterEach(() => {
    if (tempDir && fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('should return original filename if not exists', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-unique-'));
    const result = generateUniqueFileName(tempDir, 'spec', '.yaml');
    expect(result).toBe('spec.yaml');
  });

  it('should add counter if file exists', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-unique-'));
    fs.writeFileSync(path.join(tempDir, 'spec.yaml'), '');
    const result = generateUniqueFileName(tempDir, 'spec', '.yaml');
    expect(result).toBe('spec-1.yaml');
  });

  it('should increment counter for multiple collisions', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-unique-'));
    fs.writeFileSync(path.join(tempDir, 'spec.yaml'), '');
    fs.writeFileSync(path.join(tempDir, 'spec-1.yaml'), '');
    fs.writeFileSync(path.join(tempDir, 'spec-2.yaml'), '');
    const result = generateUniqueFileName(tempDir, 'spec', '.yaml');
    expect(result).toBe('spec-3.yaml');
  });

  it('should handle different extensions', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-unique-'));
    fs.writeFileSync(path.join(tempDir, 'backup.json'), '');
    const result = generateUniqueFileName(tempDir, 'backup', '.json');
    expect(result).toBe('backup-1.json');
  });
});

describe('validateBackupDirectory', () => {
  let tempDir: string;

  afterEach(() => {
    if (tempDir && fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('should validate writable directory', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-backup-'));
    expect(() => validateBackupDirectory(tempDir)).not.toThrow();
  });

  it('should create parent directory if not exists', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-backup-'));
    const subDir = path.join(tempDir, 'nested', 'dir');
    expect(() => validateBackupDirectory(subDir)).not.toThrow();
    expect(fs.existsSync(path.dirname(subDir))).toBe(true);
  });

  it('should throw if parent directory not writable', () => {
    // chmod does not restrict access on Windows
    if (process.platform === 'win32') {
      return;
    }

    // Skip test if running as root (e.g., in CI/Docker) - root can write to read-only dirs
    if (process.getuid && process.getuid() === 0) {
      // biome-ignore lint/suspicious/noConsole: Logging purpose
      console.log('Skipping permission test - running as root');
      return;
    }

    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-backup-'));
    fs.chmodSync(tempDir, 0o444); // read-only

    expect(() => validateBackupDirectory(path.join(tempDir, 'backup'))).toThrow(/Cannot write to backup directory/);

    fs.chmodSync(tempDir, 0o755); // restore permissions
  });

  it('should check disk space if available', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-backup-'));
    // Request 1TB - should fail on most systems
    expect(() => validateBackupDirectory(tempDir, 1000)).toThrow(/Insufficient disk space/);
  });

  it('should accept custom minSpaceGB', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-backup-'));
    // Request 0.001GB (1MB) - should pass
    expect(() => validateBackupDirectory(tempDir, 0.001)).not.toThrow();
  });
});

describe('moveAtomically', () => {
  let tempDir: string;

  afterEach(() => {
    if (tempDir && fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('should move directory atomically', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-atomic-'));
    const sourceDir = path.join(tempDir, 'source');
    const destDir = path.join(tempDir, 'dest');

    fs.mkdirSync(sourceDir);
    fs.writeFileSync(path.join(sourceDir, 'file.txt'), 'test');

    moveAtomically(sourceDir, destDir);

    expect(fs.existsSync(destDir)).toBe(true);
    expect(fs.existsSync(sourceDir)).toBe(false);
    expect(fs.readFileSync(path.join(destDir, 'file.txt'), 'utf8')).toBe('test');
  });

  it('should throw if destination already exists', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-atomic-'));
    const sourceDir = path.join(tempDir, 'source');
    const destDir = path.join(tempDir, 'dest');

    fs.mkdirSync(sourceDir);
    fs.writeFileSync(path.join(sourceDir, 'file.txt'), 'test');
    fs.mkdirSync(destDir);
    fs.writeFileSync(path.join(destDir, 'existing.txt'), 'existing');

    // On macOS/Linux, renameSync on directories may behave differently
    // Testing the error case requires destination to not be empty
    expect(() => moveAtomically(sourceDir, destDir)).toThrow();
  });

  it('should throw if source does not exist', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-atomic-'));
    const sourceDir = path.join(tempDir, 'nonexistent');
    const destDir = path.join(tempDir, 'dest');

    expect(() => moveAtomically(sourceDir, destDir)).toThrow();
  });

  it('should preserve file permissions', () => {
    // Executable bit is not meaningful on Windows
    if (process.platform === 'win32') {
      return;
    }

    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-atomic-'));
    const sourceDir = path.join(tempDir, 'source');
    const destDir = path.join(tempDir, 'dest');

    fs.mkdirSync(sourceDir);
    const filePath = path.join(sourceDir, 'executable.sh');
    fs.writeFileSync(filePath, '#!/bin/bash\necho test');
    fs.chmodSync(filePath, 0o755);

    moveAtomically(sourceDir, destDir);

    const destFile = path.join(destDir, 'executable.sh');
    const stats = fs.statSync(destFile);
    expect(stats.mode & 0o111).toBeTruthy(); // executable bit set
  });
});

describe('cleanupDirectory', () => {
  let tempDir: string;

  afterEach(() => {
    if (tempDir && fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  it('should remove directory if exists', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-cleanup-'));
    const targetDir = path.join(tempDir, 'to-delete');
    fs.mkdirSync(targetDir);

    cleanupDirectory(targetDir);

    expect(fs.existsSync(targetDir)).toBe(false);
  });

  it('should not throw if directory does not exist', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-cleanup-'));
    const nonExistentDir = path.join(tempDir, 'nonexistent');

    expect(() => cleanupDirectory(nonExistentDir)).not.toThrow();
  });

  it('should remove nested directories', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-cleanup-'));
    const targetDir = path.join(tempDir, 'parent');
    const nestedDir = path.join(targetDir, 'child', 'grandchild');
    fs.mkdirSync(nestedDir, { recursive: true });
    fs.writeFileSync(path.join(nestedDir, 'file.txt'), 'test');

    cleanupDirectory(targetDir);

    expect(fs.existsSync(targetDir)).toBe(false);
  });

  it('should remove files in directory', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-cleanup-'));
    const targetDir = path.join(tempDir, 'with-files');
    fs.mkdirSync(targetDir);
    fs.writeFileSync(path.join(targetDir, 'file1.txt'), 'test1');
    fs.writeFileSync(path.join(targetDir, 'file2.txt'), 'test2');

    cleanupDirectory(targetDir);

    expect(fs.existsSync(targetDir)).toBe(false);
  });

  it('should handle read-only files', () => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-cleanup-'));
    const targetDir = path.join(tempDir, 'readonly');
    fs.mkdirSync(targetDir);
    const readonlyFile = path.join(targetDir, 'readonly.txt');
    fs.writeFileSync(readonlyFile, 'test');
    fs.chmodSync(readonlyFile, 0o444);

    cleanupDirectory(targetDir);

    expect(fs.existsSync(targetDir)).toBe(false);
  });
});

describe('skill path helpers', () => {
  it('derive every skill path from the same sanitized base name', () => {
    expect(skillDirRelativePath('C++ Helper')).toBe(`skills/${sanitizeFileName('C++ Helper')}`);
    expect(skillFlatFileRelativePath('C++ Helper')).toBe(`skills/${sanitizeFileName('C++ Helper')}.skill.md`);
    expect(skillMarkdownRelativePath('C++ Helper')).toBe(`skills/${sanitizeFileName('C++ Helper')}/SKILL.md`);
  });

  it('collapse punctuation the same way for a flat file and a SKILL.md directory', () => {
    expect(skillFlatFileRelativePath('Code_Review')).toBe('skills/code-review.skill.md');
    expect(skillDirRelativePath('Code_Review')).toBe('skills/code-review');
    expect(skillMarkdownRelativePath('Code_Review')).toBe('skills/code-review/SKILL.md');
  });

  it('keep a plain name unchanged apart from lowercasing', () => {
    expect(skillFlatFileRelativePath('My Skill')).toBe('skills/my-skill.skill.md');
    expect(skillMarkdownRelativePath('My Skill')).toBe('skills/my-skill/SKILL.md');
  });
});

describe('resolvePathWithinDirectory', () => {
  it('resolves a plain relative path inside the directory', () => {
    expect(resolvePathWithinDirectory('/base/dir', 'reference.md')).toBe(path.resolve('/base/dir', 'reference.md'));
    expect(resolvePathWithinDirectory('/base/dir', 'docs/deep/reference.md')).toBe(
      path.resolve('/base/dir', 'docs/deep/reference.md')
    );
  });

  it('rejects a path escaping the directory with ..', () => {
    expect(() => resolvePathWithinDirectory('/base/dir', '../escape.txt')).toThrow(/outside/i);
    expect(() => resolvePathWithinDirectory('/base/dir', 'docs/../../escape.txt')).toThrow(/outside/i);
  });

  it('rejects an absolute path rather than silently nesting it', () => {
    expect(() => resolvePathWithinDirectory('/base/dir', '/etc/passwd')).toThrow(/outside/i);
  });

  it('rejects a path resolving to the directory itself', () => {
    expect(() => resolvePathWithinDirectory('/base/dir', '.')).toThrow(/outside/i);
  });

  it('names the offending path in the error message', () => {
    expect(() => resolvePathWithinDirectory('/base/dir', '../escape.txt')).toThrow(/\.\.\/escape\.txt/);
  });

  it('rejects a sibling directory whose name merely starts with the base name', () => {
    expect(() => resolvePathWithinDirectory('/base/dir', '../dir-other/file.txt')).toThrow(/outside/i);
  });
});
