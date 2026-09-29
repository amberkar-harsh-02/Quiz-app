// The four answer slots. Each has a shape as well as a color so they can be told apart
// without relying on color alone.
export const ANSWERS = [
  { color: 'red', shape: 'triangle', bg: '#e21b3c', text: '#ffffff' },
  { color: 'blue', shape: 'diamond', bg: '#1368ce', text: '#ffffff' },
  { color: 'yellow', shape: 'circle', bg: '#d89e00', text: '#ffffff' },
  { color: 'green', shape: 'square', bg: '#26890c', text: '#ffffff' },
];

export const answerFor = (color) => ANSWERS.find((a) => a.color === color);
