/** Difficulties offered for bot seats, easiest first; the values are the server's keys. */
export const DIFFICULTIES = [
  { value: "very-easy", label: "Very easy" },
  { value: "easy", label: "Easy" },
];

/** The display name of a difficulty key; an unknown key is shown as it is. */
export function difficultyLabel(value: string): string {
  return DIFFICULTIES.find((d) => d.value === value)?.label ?? value;
}
