import { render } from "@testing-library/react";
import OrderCard from "./OrderCard";
let props = {};
describe('Header component', () => {
    beforeEach(() => {
        props = {
            activeTabKey: "one",
            isActive: true,
            isEdit: true,
            name: "name",
            onClose: jest.fn(),
            onSaveClick: jest.fn(),
            onTabChange: jest.fn(),
            tabList: {
                key: "121",
                tab: []
            },
            toggleEdit: jest.fn()
        };
    })
    it("should rendered", () => {
        // @ts-ignore
        const x = render(<OrderCard {...props} />);

        expect(x.getByText("name")).toBeTruthy();
    });
});
