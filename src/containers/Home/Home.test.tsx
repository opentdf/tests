import { render, screen } from "@testing-library/react";
import Home from "./Home";

describe('Home component', () => {
  it("is rendered", () => {
    render(<Home />);

    expect(screen.getByText('Attributes')).toBeInTheDocument();
    expect(screen.getByText('Entities')).toBeInTheDocument();
  });
});
