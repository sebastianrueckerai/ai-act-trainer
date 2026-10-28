import parser from "@typescript-eslint/parser";

export default [
  { ignores: ["dist", "src/ui/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser },
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXOpeningElement[name.name=/^(button|input|select|textarea)$/]",
          message:
            "Raw form elements are not allowed outside src/ui. Use the primitives: Button, Chip, Select, TextArea, TextInput from src/ui.",
        },
      ],
    },
  },
];
