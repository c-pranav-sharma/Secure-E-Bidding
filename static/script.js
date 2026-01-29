


document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const pupils = document.querySelectorAll(".pupil");
  const shapes = document.querySelectorAll(".shape");
  const passwordInput = document.getElementById("password");
  const togglePasswordBtn = document.getElementById("togglePassword");
  const toggleIcon = document.getElementById("toggleIcon");
  const toggleText = document.getElementById("toggleText");
  const charactersBox = document.getElementById("characters");

  if (!pupils.length || !shapes.length || !passwordInput || !togglePasswordBtn || !charactersBox) {
    console.error("Some elements not found. Check HTML ids/classes.");
    return;
  }

  let isShy = false;
  const maxOffset = 6;

  // Initial mouse position: center of characters box
  const rect = charactersBox.getBoundingClientRect();
  let mouseX = rect.left + rect.width / 2;
  let mouseY = rect.top + rect.height / 2;
  let lastMouseX = mouseX;
  let lastMouseY = mouseY;

  // Eyes follow mouse
  function lookAt(x, y) {
    pupils.forEach((pupil) => {
      const eyeRect = pupil.parentElement.getBoundingClientRect();
      const eyeCenterX = eyeRect.left + eyeRect.width / 2;
      const eyeCenterY = eyeRect.top + eyeRect.height / 2;

      const dx = x - eyeCenterX;
      const dy = y - eyeCenterY;

      const angle = Math.atan2(dy, dx);
      const offsetX = Math.cos(angle) * maxOffset;
      const offsetY = Math.sin(angle) * maxOffset;

      pupil.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
    });
  }

  // Characters tilt (pivot from bottom)
  function moveCharacters(x) {
    const boxRect = charactersBox.getBoundingClientRect();
    const centerX = boxRect.left + boxRect.width / 2;
    const relX = (x - centerX) / boxRect.width; // roughly -0.5..0.5

    shapes.forEach((shape, index) => {
      const baseTilt = 6;          // degrees
      const extraTilt = index * 2; // each shape slightly different
      const angle = relX * (baseTilt + extraTilt);
      shape.style.transform = `rotate(${angle}deg)`;
    });
  }

  // Animation loop
  function animateCharacters() {
    if (!isShy) {
      lastMouseX += (mouseX - lastMouseX) * 0.12;
      lastMouseY += (mouseY - lastMouseY) * 0.12;

      moveCharacters(lastMouseX);
      lookAt(lastMouseX, lastMouseY);
    }
    requestAnimationFrame(animateCharacters);
  }

  window.addEventListener("mousemove", (e) => {
    if (isShy) return;
    mouseX = e.clientX;
    mouseY = e.clientY;
  });

  // Show/hide password → characters turn away
  function setShy(state) {
    isShy = state;
    if (isShy) {
      shapes.forEach((shape) => {
        shape.style.transform = "rotate(-15deg)";
      });
      pupils.forEach((pupil) => {
        pupil.style.transform = `translate(${-maxOffset}px, 0px)`; // look away left
      });
    } else {
      shapes.forEach((shape) => {
        shape.style.transform = "rotate(0deg)";
      });
    }
  }

  togglePasswordBtn.addEventListener("click", () => {
    const currentlyHidden = passwordInput.type === "password";
    passwordInput.type = currentlyHidden ? "text" : "password";
    toggleText.textContent = currentlyHidden ? "Hide" : "Show";
    toggleIcon.textContent = currentlyHidden ? "🙈" : "👁";
    setShy(currentlyHidden);
  });

  // Initial slight off-center look
  lookAt(rect.right + 80, rect.top + rect.height / 2);

  // Start animation
  animateCharacters();
});




