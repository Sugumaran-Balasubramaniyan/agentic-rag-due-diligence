import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders an accessible deterministic shell without external services", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Due-Diligence Copilot" }),
    ).toBeVisible();
    expect(screen.getByText("Deterministic demo mode")).toBeVisible();
  });
});
