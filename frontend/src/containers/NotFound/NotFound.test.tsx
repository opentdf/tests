import { render, screen } from "@testing-library/react";
import NotFound from "./NotFound";
import { BrowserRouter as Router } from "react-router-dom";

describe('NotFound component', () => {
  it("is rendered", () => {
    render(
      <Router>
        <NotFound />
      </Router>
    );

    expect(screen.getByText('NotFound')).toBeInTheDocument();
    expect(screen.getByText('Go home')).toBeInTheDocument();
  });
});
