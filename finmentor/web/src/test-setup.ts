import "@testing-library/jest-dom/vitest";

/**
 * A working `localStorage`.
 *
 * Neither environment supplies one here: Node 26 defines a global that is
 * inert unless the process was started with --localstorage-file, and jsdom 25
 * under this Node does not install one on `window` either. The client stores
 * its refresh token there, so without this every storage assertion fails for a
 * reason that has nothing to do with the code under test.
 *
 * This is a faithful implementation of the bits the Storage interface actually
 * promises — string keys, string values, and `clear()` — which is all the app
 * uses.
 */
class MemoryStorage implements Storage {
  private entries = new Map<string, string>();

  get length(): number {
    return this.entries.size;
  }

  key(index: number): string | null {
    return [...this.entries.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    return this.entries.get(String(key)) ?? null;
  }

  setItem(key: string, value: string): void {
    this.entries.set(String(key), String(value));
  }

  removeItem(key: string): void {
    this.entries.delete(String(key));
  }

  clear(): void {
    this.entries.clear();
  }

  [name: string]: unknown;
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, name, {
    value: storage, configurable: true, writable: true,
  });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, name, {
      value: storage, configurable: true, writable: true,
    });
  }
}
