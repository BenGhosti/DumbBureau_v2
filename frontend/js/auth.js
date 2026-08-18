window.Auth = (() => {
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

  async function register({ username, email, inviteToken, adminSecret }) {
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
    });
    Storage.save(result);
    return result;
  }

  async function login({ username }) {
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

  function logout() {
    Storage.clear();
  }

  return { register, login, logout };
})();
