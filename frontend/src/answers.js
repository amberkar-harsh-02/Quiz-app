// The four answer slots. Each has a shape as well as a color so they can be told apart
// without relying on color alone.
export const ANSWERS = [
  { color: 'red', shape: 'triangle', bg: '#e21b3c', text: '#ffffff' },
  { color: 'blue', shape: 'diamond', bg: '#1368ce', text: '#ffffff' },
  // White on this yellow is under 3:1 contrast, so it takes dark text
  { color: 'yellow', shape: 'circle', bg: '#d89e00', text: '#172033' },
  { color: 'green', shape: 'square', bg: '#26890c', text: '#ffffff' },
];

export const answerFor = (color) => ANSWERS.find((a) => a.color === color);
