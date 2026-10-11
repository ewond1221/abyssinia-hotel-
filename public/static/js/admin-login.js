const loginForm = document.getElementById("loginForm");
const errorMessage = document.getElementById("errorMessage");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch("/api/auth/admin/login", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        username,
        password,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      errorMessage.textContent = data.error;
      return;
    }

    localStorage.setItem("adminToken", data.token);

    window.location.href = "/admin/dashboard";
  } catch (error) {
    console.error(error);
    errorMessage.textContent = "Something went wrong.";
  }
});
