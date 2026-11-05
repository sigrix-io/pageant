// Notebook: a note written in the box goes to the top of the list, and the count follows it.
(() => {
  const form = document.getElementById("new-note");
  const input = document.getElementById("note");
  const notes = document.getElementById("notes");
  const count = document.getElementById("count");
  const counted = () => {
    const kept = notes.children.length;
    count.textContent = kept === 1 ? "1 note" : kept + " notes";
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const item = document.createElement("li");
    item.className = "fresh";
    const words = document.createElement("span");
    words.className = "text";
    words.textContent = text;
    const when = document.createElement("time");
    when.textContent = "Just now";
    item.append(words, when);
    notes.prepend(item);
    input.value = "";
    counted();
  });
  counted();
})();
