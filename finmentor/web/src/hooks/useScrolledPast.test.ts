/**
 * The one thing worth testing here is the direction check: an element that has
 * not been reached yet and one that has been scrolled past both report
 * `isIntersecting: false`, and telling them apart is the entire reason this
 * hook exists rather than a one-line `useInView` call.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useScrolledPast } from "./useScrolledPast";

type Callback = (entries: IntersectionObserverEntry[]) => void;

let fire: Callback;
const disconnect = vi.fn();

/** jsdom ships no IntersectionObserver, so the test supplies one it can drive:
 * `fire` stands in for the browser deciding the element moved. */
class FakeObserver {
  constructor(callback: Callback) {
    fire = callback;
  }
  observe() {}
  disconnect() {
    disconnect();
  }
  unobserve() {}
}

function entry(isIntersecting: boolean, top: number): IntersectionObserverEntry {
  return { isIntersecting, boundingClientRect: { top } } as IntersectionObserverEntry;
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  disconnect.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The hook only observes once it has an element, so the test gives it one. */
function mount() {
  const result = renderHook(() => {
    const hook = useScrolledPast<HTMLDivElement>();
    hook.ref.current ??= document.createElement("div");
    return hook;
  });
  // The ref is assigned during the first render; the effect runs after it.
  result.rerender();
  return result;
}

describe("useScrolledPast", () => {
  it("starts false", () => {
    expect(mount().result.current.past).toBe(false);
  });

  it("is true once the element is above the viewport", () => {
    const { result } = mount();
    act(() => fire([entry(false, -240)]));
    expect(result.current.past).toBe(true);
  });

  it("stays false for an element that is below the viewport, not above it", () => {
    const { result } = mount();
    act(() => fire([entry(false, 900)]));
    expect(result.current.past).toBe(false);
  });

  it("comes back to false when the element scrolls into view again", () => {
    const { result } = mount();
    act(() => fire([entry(false, -240)]));
    act(() => fire([entry(true, 12)]));
    expect(result.current.past).toBe(false);
  });

  it("disconnects on unmount", () => {
    mount().unmount();
    expect(disconnect).toHaveBeenCalled();
  });
});
