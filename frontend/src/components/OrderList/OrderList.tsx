import { FC, useRef } from "react";

type Props = {
  list: string[];
  onReorder: (list: string[]) => void;
};

const OrderList: FC<Props> = (props) => {
  const { list, onReorder } = props;

  const draggingItem = useRef<{ key: string; index: number }>();
  const dragOverItem = useRef<{ key: string; index: number }>();

  const handleDragStart = (
    e: React.DragEvent<HTMLLIElement>,
    key: string,
    index: number,
  ) => {
    draggingItem.current = { key, index };
  };

  const handleDragEnter = (
    e: React.DragEvent<HTMLLIElement>,
    key: string,
    index: number,
  ) => {
    dragOverItem.current = { key, index };
  };

  const handleDragEnd = (e: React.DragEvent<HTMLLIElement>) => {
    const newList = [...list];
    const draggingItemCurrent = draggingItem.current;
    const dragOverItemCurrent = dragOverItem.current;

    if (!draggingItemCurrent || !dragOverItemCurrent) {
      return;
    }

    newList[dragOverItemCurrent?.index] = draggingItemCurrent?.key;
    newList[draggingItemCurrent?.index] = dragOverItemCurrent?.key;

    draggingItem.current = undefined;
    dragOverItem.current = undefined;
    onReorder(newList);
  };

  return (
    <ul className="order-list">
      {list.map((item, index) => (
        <li
          className="order-list__item"
          draggable
          key={item}
          onDragEnd={handleDragEnd}
          onDragEnter={(e) => handleDragEnter(e, item, index)}
          onDragOver={(e) => e.preventDefault()}
          onDragStart={(e) => handleDragStart(e, item, index)}
        >
          {item}
        </li>
      ))}
    </ul>
  );
};

export default OrderList;
