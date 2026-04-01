import { TextInput } from "./text-input";

export function SearchInput(props: Omit<Parameters<typeof TextInput>[0], "type">) {
  return <TextInput type="search" placeholder="Search" {...props} />;
}
