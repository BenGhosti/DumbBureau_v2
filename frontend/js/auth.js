window.Auth = (() => {
  let conditionalAbortController = null;

  function decodeCreationOptions(options) {
    return {
      challenge: Utils.b64urlToArrayBuffer(options.challenge),
      rp: options.rp,
      user: { ...options.user, id: Utils.b64urlToArrayBuffer(options.user.id) },
      pubKeyCredParams: options.pubKeyCredParams,
      timeout: options.timeout,
      attestation: options.attestation,
      authenticatorSelection: options.authenticatorSelection,
      excludeCredentials: (options.excludeCredentials || []).map((c) => ({
        ...c,
        id: Utils.b64urlToArrayBuffer(c.id),
      })),
    };
  }

  function decodeRequestOptions(options) {
    return {
      challenge: Utils.b64urlToArrayBuffer(options.challenge),
      rpId: options.rpId,
      timeout: options.timeout,
      userVerification: options.userVerification,
      allowCredentials: (options.allowCredentials || []).map((c) => ({
        ...c,
        id: Utils.b64urlToArrayBuffer(c.id),
      })),
    };
  }

  function serializeCreation(cred) {
    return {
      id: cred.id,
      rawId: Utils.arrayBufferToB64url(cred.rawId),
      response: {
        clientDataJSON: Utils.arrayBufferToB64url(cred.response.clientDataJSON),
        attestationObject: Utils.arrayBufferToB64url(cred.response.attestationObject),
      },
      type: cred.type,
    };
  }

  function serializeAssertion(cred) {
    return {
      id: cred.id,
      rawId: Utils.arrayBufferToB64url(cred.rawId),
      response: {
        clientDataJSON: Utils.arrayBufferToB64url(cred.response.clientDataJSON),
        authenticatorData: Utils.arrayBufferToB64url(cred.response.authenticatorData),
        signature: Utils.arrayBufferToB64url(cred.response.signature),
        userHandle: cred.response.userHandle
          ? Utils.arrayBufferToB64url(cred.response.userHandle)
          : null,
      },
      type: cred.type,
    };
  }

  function ensureWebAuthn() {
    if (!window.PublicKeyCredential || !navigator.credentials) {
      throw new Error(I18n.t('webauthn_unsupported'));
    }
  }

  async function register({ username, email, inviteToken, adminSecret, passkeyName }) {
    ensureWebAuthn();
    const opts = await Api.post('/auth/register/options', {
      username,
      email: email || null,
      invite_token: inviteToken || null,
      admin_secret: adminSecret || null,
    });
    const cred = await navigator.credentials.create({
      publicKey: decodeCreationOptions(opts.options),
    });
    const result = await Api.post('/auth/register/verify', {
      challenge_id: opts.challenge_id,
      credential: serializeCreation(cred),
      passkey_name: passkeyName || null,
    });
    Storage.save(result);
    return result;
  }

  async function login({ username } = {}) {
    ensureWebAuthn();
    const opts = await Api.post('/auth/login/options', { username: username || null });
    const cred = await navigator.credentials.get({
      publicKey: decodeRequestOptions(opts.options),
    });
    const result = await Api.post('/auth/login/verify', {
      challenge_id: opts.challenge_id,
      credential: serializeAssertion(cred),
    });
    Storage.save(result);
    return result;
  }

  // Usernameless login via the browser's native autofill UI: fires a
  // background WebAuthn request the moment the page loads. It stays
  // pending (no dialog shown) until the user interacts with an
  // autocomplete="username webauthn" input and picks a suggested passkey -
  // at which point this promise resolves and completes the login exactly
  // like a normal button-triggered one. Call abortConditional() before
  // starting a new one (e.g. on page navigation) to avoid leaking pending
  // requests; a second concurrent conditional request throws otherwise.
  async function loginConditional(onSuccess, onError) {
    ensureWebAuthn();
    if (!window.PublicKeyCredential?.isConditionalMediationAvailable) return;
    const available = await PublicKeyCredential.isConditionalMediationAvailable();
    if (!available) return;

    abortConditional();
    conditionalAbortController = new AbortController();

    try {
      const opts = await Api.post('/auth/login/options', { username: null });
      const cred = await navigator.credentials.get({
        publicKey: decodeRequestOptions(opts.options),
        mediation: 'conditional',
        signal: conditionalAbortController.signal,
      });
      const result = await Api.post('/auth/login/verify', {
        challenge_id: opts.challenge_id,
        credential: serializeAssertion(cred),
      });
      Storage.save(result);
      onSuccess?.(result);
    } catch (err) {
      // AbortError is expected whenever we intentionally cancel (page
      // navigation, explicit submit taking over) - not a real failure.
      if (err?.name === 'AbortError') return;
      onError?.(err);
    }
  }

  function abortConditional() {
    if (conditionalAbortController) {
      conditionalAbortController.abort();
      conditionalAbortController = null;
    }
  }

  function logout() {
    Storage.clear();
  }

  async function addPasskey(passkeyName) {
    ensureWebAuthn();
    const opts = await Api.post('/auth/passkeys/add/options', {});
    const cred = await navigator.credentials.create({
      publicKey: decodeCreationOptions(opts.options),
    });
    return Api.post('/auth/passkeys/add/verify', {
      challenge_id: opts.challenge_id,
      credential: serializeCreation(cred),
      passkey_name: passkeyName || null,
    });
  }

  async function removePasskey(passkeyId) {
    ensureWebAuthn();
    const opts = await Api.post('/auth/passkeys/' + passkeyId + '/remove/options', {});
    // The server only offers the ONE credential being removed as an
    // allowed option (see backend remove_passkey_options) - the browser's
    // picker will only let the user complete this with that exact passkey,
    // enforcing "you can only remove a passkey by proving you have it".
    const cred = await navigator.credentials.get({
      publicKey: decodeRequestOptions(opts.options),
    });
    return Api.post('/auth/passkeys/' + passkeyId + '/remove/verify', {
      challenge_id: opts.challenge_id,
      credential: serializeAssertion(cred),
    });
  }

  return {
    register,
    login,
    loginConditional,
    abortConditional,
    logout,
    addPasskey,
    removePasskey,
  };
})();
