const form = document.querySelector('#login-form');
const errorEl = document.querySelector('#login-error');

form.addEventListener('submit', async event => {
  event.preventDefault();
  errorEl.textContent = '';
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: form.password.value})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Anmeldung fehlgeschlagen.');
    form.password.value = '';
    window.location.replace('/');
  } catch (error) {
    errorEl.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
