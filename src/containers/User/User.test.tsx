import { render, screen } from "@testing-library/react";
import User from "./User";
import { BrowserRouter as Router } from "react-router-dom";

describe('User component', () => {
  it("is rendered", () => {
    render(
      <Router>
        <User />
      </Router>
    );

    expect(screen.getByText('User')).toBeInTheDocument();
  });
});
