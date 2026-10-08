import { Pressable, Text, TextInput, View } from "react-native";

import { styles } from "./insightsStyles";

export function ValueField({
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
  keyboardType = "default",
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  keyboardType?: "default" | "numeric";
  disabled?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        multiline={multiline}
        editable={!disabled}
        keyboardType={keyboardType}
        autoCapitalize={multiline ? "sentences" : "none"}
        style={[styles.input, multiline && styles.multiline]}
      />
    </View>
  );
}

export function SelectButton({
  label,
  selected,
  onPress,
  disabled = false,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

export { formatInsightValue } from "../state";
