// alert.js

// Function to display an alert box with a given message
function showAlert(message) {
  alert(message);
}

// Get the value of the password and re-entered password fields
var password = document.getElementById("password").value;
var repassword = document.getElementById("repassword").value;

// Check if the passwords match
if (password !== repassword) {
  // Call the showAlert function with the error message
  showAlert("Passwords do not match. Please enter the same password.");
}
