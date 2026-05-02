// DOM Elements
const translationForm = document.getElementById("translation-form");
const inputSection = document.getElementById("input-section");
const progressSection = document.getElementById("progress-section");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");

const articleTitleInput = document.getElementById("article-title");
const thaiTitleInput = document.getElementById("thai-title");
const customGlossaryInput = document.getElementById("custom-glossary");
const submitBtn = document.getElementById("submit-btn");

const statusMessage = document.getElementById("status-message");
const jobTitle = document.getElementById("job-title");
const jobThaiTitle = document.getElementById("job-thai-title");
const jobIdElement = document.getElementById("job-id");
const cancelBtn = document.getElementById("cancel-btn");

const translationResult = document.getElementById("translation-result");
const copyBtn = document.getElementById("copy-btn");
const downloadBtn = document.getElementById("download-btn");
const newTranslationBtn = document.getElementById("new-translation-btn");

const errorMessage = document.getElementById("error-message");
const tryAgainBtn = document.getElementById("try-again-btn");

// Global variables
let currentJobId = null;
let statusCheckInterval = null;
let lastStatus = null;
let csrfToken = null;

// Fetch CSRF token on page load
async function fetchCsrfToken() {
  try {
    const response = await fetch("/api/csrf-token");
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Failed to fetch CSRF token");
    }

    csrfToken = data.token;
  } catch (error) {
    console.error("Error fetching CSRF token:", error);
    showError(
      "Failed to initialize security features. Please refresh the page."
    );
  }
}

// Event Listeners
document.addEventListener("DOMContentLoaded", () => {
  // Fetch CSRF token first
  fetchCsrfToken();

  translationForm.addEventListener("submit", handleFormSubmit);
  cancelBtn.addEventListener("click", cancelTranslation);
  copyBtn.addEventListener("click", copyToClipboard);
  downloadBtn.addEventListener("click", downloadResult);
  newTranslationBtn.addEventListener("click", startNewTranslation);
  tryAgainBtn.addEventListener("click", startNewTranslation);
});

// Form submission handler
async function handleFormSubmit(event) {
  event.preventDefault();

  // Get form values
  const title = articleTitleInput.value.trim();
  const thTitle = thaiTitleInput.value.trim();
  const glossary = customGlossaryInput.value.trim();

  // Validate inputs
  if (!title || !thTitle) {
    showError("Please enter both English and Thai article titles.");
    return;
  }

  // Check if CSRF token is available
  if (!csrfToken) {
    showError("Security token not available. Please refresh the page.");
    return;
  }

  // Disable form and show progress section
  submitBtn.disabled = true;
  showSection(progressSection);

  try {
    // Submit translation request
    const response = await fetch("/api/translate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({
        title: title,
        th_title: thTitle,
        glossary: glossary,
      }),
      credentials: "same-origin",
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Failed to start translation");
    }

    // Store job ID and start checking status
    currentJobId = data.job_id;
    jobTitle.textContent = title;
    jobThaiTitle.textContent = thTitle;
    jobIdElement.textContent = currentJobId;

    // Start polling for status updates
    startStatusChecking();
  } catch (error) {
    showError(error.message);
    submitBtn.disabled = false;
  }
}

// Start checking translation status
function startStatusChecking() {
  // Clear any existing interval
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
  }

  // Check immediately
  checkTranslationStatus();

  // Then check every 3 seconds
  statusCheckInterval = setInterval(checkTranslationStatus, 3000);
}

// Check translation status
async function checkTranslationStatus() {
  if (!currentJobId) return;

  try {
    const response = await fetch(`/api/status/${currentJobId}`, {
      credentials: "same-origin",
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Failed to check translation status");
    }

    // Update status message
    updateStatusMessage(data.status);

    // If status changed to completed or error, handle accordingly
    if (data.status !== lastStatus) {
      lastStatus = data.status;

      if (data.status === "completed") {
        clearInterval(statusCheckInterval);
        fetchTranslationResult();
      } else if (data.status === "error") {
        clearInterval(statusCheckInterval);
        showError(data.error || "An error occurred during translation");
      }
    }
  } catch (error) {
    clearInterval(statusCheckInterval);
    showError(error.message);
  }
}

// Update status message based on current status
function updateStatusMessage(status) {
  switch (status) {
    case "queued":
      statusMessage.textContent = "Translation queued, waiting to start...";
      break;
    case "processing":
      statusMessage.textContent = "Translating article...";
      break;
    case "completed":
      statusMessage.textContent = "Translation completed!";
      break;
    case "error":
      statusMessage.textContent = "Error occurred during translation.";
      break;
    default:
      statusMessage.textContent = "Unknown status";
  }
}

// Fetch translation result
async function fetchTranslationResult() {
  try {
    const response = await fetch(`/api/result/${currentJobId}`, {
      credentials: "same-origin",
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Failed to fetch translation result");
    }

    // Display result
    translationResult.textContent = data.result;
    showSection(resultSection);
  } catch (error) {
    showError(error.message);
  }
}

// Cancel translation
function cancelTranslation() {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
  }

  currentJobId = null;
  lastStatus = null;
  submitBtn.disabled = false;
  showSection(inputSection);
}

// Copy result to clipboard
function copyToClipboard() {
  const text = translationResult.textContent;

  if (!text) {
    return;
  }

  navigator.clipboard
    .writeText(text)
    .then(() => {
      // Show temporary success message
      const originalText = copyBtn.textContent;
      copyBtn.textContent = "Copied!";

      setTimeout(() => {
        copyBtn.textContent = originalText;
      }, 2000);
    })
    .catch((err) => {
      console.error("Failed to copy text: ", err);
    });
}

// Download result as text file
function downloadResult() {
  const text = translationResult.textContent;

  if (!text) {
    return;
  }

  // Create a blob with the text content
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);

  // Create a temporary link and trigger download
  const a = document.createElement("a");
  a.href = url;
  a.download = `${jobTitle.textContent}_th.txt`;
  document.body.appendChild(a);
  a.click();

  // Clean up
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 0);
}

// Start a new translation
function startNewTranslation() {
  // Reset form
  translationForm.reset();

  // Reset state
  currentJobId = null;
  lastStatus = null;

  // Refresh CSRF token
  fetchCsrfToken();

  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
  }

  // Enable submit button
  submitBtn.disabled = false;

  // Show input section
  showSection(inputSection);
}

// Show error message
function showError(message) {
  errorMessage.textContent = message;
  showSection(errorSection);

  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
  }
}

// Show a specific section and hide others
function showSection(sectionToShow) {
  // Hide all sections
  inputSection.classList.add("hidden");
  progressSection.classList.add("hidden");
  resultSection.classList.add("hidden");
  errorSection.classList.add("hidden");

  // Show the requested section
  sectionToShow.classList.remove("hidden");
}
