import { describe, expect, it } from "vitest";
import { parseSseFrames } from "@/lib/api";

describe("parseSseFrames", () => {
  it("parses complete frames and keeps partial rest", () => {
    const parsed = parseSseFrames(
      'event: delta\ndata: {"text":"hello"}\n\nevent: approval\ndata: {"id":1}',
    );

    expect(parsed.frames).toEqual([{ event: "delta", data: { text: "hello" } }]);
    expect(parsed.rest).toBe('event: approval\ndata: {"id":1}');
  });
});
