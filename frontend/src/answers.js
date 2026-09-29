// The four answer slots. `color` is the key stored in the database and sent over the socket;
// students see the letter and tile color. Each letter is a non-color marker, so answers can be
// told apart without relying on color, and all four take white text at 4.5:1 or better.
export const ANSWERS = [
  { color: 'red', letter: 'A', bg: '#3949AB', text: '#ffffff' },    // indigo
  { color: 'blue', letter: 'B', bg: '#00796B', text: '#ffffff' },   // teal
  { color: 'yellow', letter: 'C', bg: '#B8520A', text: '#ffffff' }, // burnt orange
  { color: 'green', letter: 'D', bg: '#AD1457', text: '#ffffff' },  // magenta
];

export const answerFor = (color) => ANSWERS.find((a) => a.color === color);
