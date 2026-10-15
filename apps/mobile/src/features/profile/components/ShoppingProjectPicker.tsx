import { Text } from "react-native";

import { ActionButton } from "./Ui";

export type ShoppingProjectChoice = {
  project_id: string;
  label: string;
  revision: number;
};

export function ShoppingProjectPicker({
  choices,
  selectedId,
  disabled,
  onSelect,
}: {
  choices: ShoppingProjectChoice[];
  selectedId: string;
  disabled: boolean;
  onSelect: (projectId: string) => void;
}) {
  if (choices.length === 0) {
    return <Text>No active Shopping projects are available.</Text>;
  }
  return (
    <>
      {choices.map((project) => (
        <ActionButton
          key={project.project_id}
          label={`${selectedId === project.project_id ? "Selected: " : "Select: "}${project.label} (revision ${project.revision})`}
          disabled={disabled}
          onPress={() => onSelect(project.project_id)}
        />
      ))}
    </>
  );
}
