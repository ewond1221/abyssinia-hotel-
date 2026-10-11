const menuItemsContainer = document.getElementById("menuItemsContainer");
const menuErrorMessage = document.getElementById("menuErrorMessage");
const addMenuItemButton = document.getElementById("addMenuItemButton");
const logoutButton = document.getElementById("logoutButton");

const token = localStorage.getItem("adminToken");

if (!token) {
  window.location.href = "/admin/login";
}

if (logoutButton) {
  logoutButton.addEventListener("click", () => {
    localStorage.removeItem("adminToken");
    window.location.href = "/admin/login";
  });
}

const MENU_CATEGORIES = [
  { value: "starters", label: "Starters" },
  { value: "main-course", label: "Main Course" },
  { value: "desserts", label: "Desserts" },
];

function menuItemViewHtml(item) {
  return `
    <h3>${escapeHtml(item.name)}</h3>
    <p><strong>Category:</strong> ${escapeHtml(item.category)}</p>
    <p><strong>Price:</strong> ETB ${Number(item.price).toFixed(2)}</p>
    <p><strong>Description:</strong> ${escapeHtml(item.desc)}</p>
    <p><strong>Image path:</strong> ${escapeHtml(item.img)}</p>
    <div class="menu-item-actions">
      <button type="button" class="edit-menu-item-button" data-item-id="${escapeHtml(item.id)}">
        Edit
      </button>
      <button type="button" class="delete-menu-item-button" data-item-id="${escapeHtml(item.id)}">
        Delete
      </button>
    </div>
  `;
}

function menuItemEditHtml(item) {
  const categoryOptions = MENU_CATEGORIES.map(
    (cat) => `<option value="${cat.value}" ${cat.value === item.category ? "selected" : ""}>${cat.label}</option>`
  ).join("");

  return `
    <div class="form-group">
      <label>Name</label>
      <input type="text" class="edit-name" value="${escapeHtml(item.name)}" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <input type="text" class="edit-desc" value="${escapeHtml(item.desc)}" />
    </div>
    <div class="form-group">
      <label>Price</label>
      <input type="number" class="edit-price" min="0" step="0.01" value="${Number(item.price)}" />
    </div>
    <div class="form-group">
      <label>Category</label>
      <select class="edit-category">${categoryOptions}</select>
    </div>
    <div class="form-group">
      <label>Image path</label>
      <input type="text" class="edit-img" value="${escapeHtml(item.img)}" />
    </div>
    <p class="error-message edit-menu-item-error"></p>
    <div class="menu-item-actions">
      <button type="button" class="save-menu-item-button" data-item-id="${escapeHtml(item.id)}">
        Save
      </button>
      <button type="button" class="cancel-menu-item-button" data-item-id="${escapeHtml(item.id)}">
        Cancel
      </button>
    </div>
  `;
}

async function loadMenuItems() {
  try {
    const response = await fetch("/api/menu");
    const items = await response.json();

    menuItemsContainer.innerHTML = "";

    if (items.length === 0) {
      menuItemsContainer.textContent = "No menu items found.";
      return;
    }

    items.forEach((item) => {
      const itemElement = document.createElement("div");
      itemElement.classList.add("order-card");
      itemElement.dataset.itemId = item.id;
      itemElement.innerHTML = menuItemViewHtml(item);
      menuItemsContainer.appendChild(itemElement);
    });

    menuItemsContainer.querySelectorAll(".edit-menu-item-button").forEach((button) => {
      button.addEventListener("click", () => {
        const itemId = button.dataset.itemId;
        const currentItem = items.find((i) => i.id === itemId);
        const card = menuItemsContainer.querySelector(`[data-item-id="${itemId}"]`);

        card.innerHTML = menuItemEditHtml(currentItem);

        card.querySelector(".save-menu-item-button").addEventListener("click", async () => {
          const errorEl = card.querySelector(".edit-menu-item-error");
          errorEl.textContent = "";

          const updated = {
            name: card.querySelector(".edit-name").value.trim(),
            desc: card.querySelector(".edit-desc").value.trim(),
            price: card.querySelector(".edit-price").value,
            category: card.querySelector(".edit-category").value,
            img: card.querySelector(".edit-img").value.trim(),
          };

          if (!updated.name || !updated.desc || !updated.price || !updated.img) {
            errorEl.textContent = "All fields are required.";
            return;
          }

          try {
            const response = await fetch(`/api/admin/menu/${itemId}`, {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify(updated),
            });

            if (response.status === 401 || response.status === 403) {
              localStorage.removeItem("adminToken");
              window.location.href = "/admin/login";
              return;
            }

            const data = await response.json();

            if (!response.ok) {
              errorEl.textContent = data.error || "Failed to update menu item";
              return;
            }

            await loadMenuItems();
          } catch (error) {
            console.error("Update menu item error:", error);
            errorEl.textContent = "Something went wrong while updating the item.";
          }
        });

        card.querySelector(".cancel-menu-item-button").addEventListener("click", () => {
          loadMenuItems();
        });
      });
    });

    document.querySelectorAll(".delete-menu-item-button").forEach((button) => {
      button.addEventListener("click", async () => {
        const itemId = button.dataset.itemId;
        const confirmed = window.confirm("Delete this menu item?");

        if (!confirmed) {
          return;
        }

        try {
          const response = await fetch(`/api/admin/menu/${itemId}`, {
            method: "DELETE",
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.status === 401 || response.status === 403) {
            localStorage.removeItem("adminToken");
            window.location.href = "/admin/login";
            return;
          }

          if (!response.ok) {
            const data = await response.json();
            alert(data.error || "Failed to delete menu item");
            return;
          }

          await loadMenuItems();
        } catch (error) {
          console.error("Delete menu item error:", error);
          alert("Something went wrong while deleting the item.");
        }
      });
    });
  } catch (error) {
    console.error("Load menu items error:", error);
    menuItemsContainer.textContent = "Unable to load menu items.";
  }
}

if (addMenuItemButton) {
  addMenuItemButton.addEventListener("click", async () => {
    const item = {
      id: document.getElementById("newItemId").value.trim(),
      name: document.getElementById("newItemName").value.trim(),
      desc: document.getElementById("newItemDesc").value.trim(),
      price: document.getElementById("newItemPrice").value,
      category: document.getElementById("newItemCategory").value,
      img: document.getElementById("newItemImg").value.trim(),
    };

    menuErrorMessage.textContent = "";

    if (!item.id || !item.name || !item.desc || !item.price || !item.img) {
      menuErrorMessage.textContent = "All fields are required to add a menu item.";
      return;
    }

    try {
      const response = await fetch("/api/admin/menu", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(item),
      });

      if (response.status === 401 || response.status === 403) {
        localStorage.removeItem("adminToken");
        window.location.href = "/admin/login";
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        menuErrorMessage.textContent = data.error || "Failed to add menu item";
        return;
      }

      document.getElementById("newItemId").value = "";
      document.getElementById("newItemName").value = "";
      document.getElementById("newItemDesc").value = "";
      document.getElementById("newItemPrice").value = "";
      document.getElementById("newItemImg").value = "";

      await loadMenuItems();
    } catch (error) {
      console.error("Add menu item error:", error);
      menuErrorMessage.textContent = "Something went wrong while adding the item.";
    }
  });
}

loadMenuItems();
