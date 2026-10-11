export const API_KEY_TUTORIAL_REQUEST = 'fg_open_api_key_tutorial';

export function requestApiKeyTutorial() {
  sessionStorage.setItem(API_KEY_TUTORIAL_REQUEST, 'true');
}

export function consumeApiKeyTutorialRequest() {
  const requested = sessionStorage.getItem(API_KEY_TUTORIAL_REQUEST) === 'true';
  if (requested) sessionStorage.removeItem(API_KEY_TUTORIAL_REQUEST);
  return requested;
}
