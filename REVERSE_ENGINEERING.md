# Engenharia reversa — Nintendo (26/11/2026)

Fontes: `accounts.nintendo.com` (browser), APK **Nintendo Switch Parental Controls 2.7.0** (`com.nintendo.znma`, build 740, jadx), nxapi/pynintendoparental como referência.

## Login
- `POST https://accounts.nintendo.com/login` (campos `subject_id`, `subject_password`, `csrf_token`…) é protegido por **Akamai Bot Manager** (`_abck` + sensor JS). Cliente HTTP puro recebe `302 → /cdn/display_error?error=retry`. Contornar exigiria forjar o sensor anti-bot — não feito.
- Login a partir de ambiente novo → Nintendo manda e-mail "código de confirmação" (6 dígitos, 1 h). Conta sem 2FA.
- Caminho usado (o dos apps oficiais): OAuth `session_token_code` + PKCE.
  - `GET /connect/1.0.0/authorize?client_id=54789befb391a838&redirect_uri=npf54789befb391a838://auth&response_type=session_token_code&session_token_code_challenge=…&scope=openid user user.mii moon…`
  - botão "Usar esta conta" = `npf54789befb391a838://auth#session_token_code=…`
  - `POST /connect/1.0.0/api/session_token` (form: client_id, session_token_code, session_token_code_verifier) → `session_token`
  - `POST /connect/1.0.0/api/token` (json: client_id, session_token, grant_type `urn:ietf:params:oauth:grant-type:jwt-bearer-session-token`) → `id_token`, `access_token` (900 s)
  - endpoints `/connect/1.0.0/api/*` não têm Akamai.

## Moon (`https://app.lp1.znma.srv.nintendo.net`)
- **Bearer = id_token** nas rotas v2/v3 (interceptor `ls.java`; v1 usaria outro token). access_token → 403 `forbidden`.
- Headers: `X-Moon-App-Id: com.nintendo.znma`, `X-Moon-Os`, `X-Moon-Os-Version`, `X-Moon-Model`, `X-Moon-TimeZone`, `X-Moon-Os-Language`, `X-Moon-App-Language`, `X-Moon-App-Display-Version: 2.7.0`, `X-Moon-App-Internal-Version: 740`, UA `moon_ANDROID/2.7.0 (com.nintendo.znma; build:740; ANDROID 34)`.
- Rotas (interface Retrofit `vk.java`): `GET /v2/actions/user/fetchUser`, `GET /v3/actions/user/fetchOwnedDevices`, `GET /v3/actions/user/fetchOwnedDevice?deviceId`, `GET /v2/actions/playSummary/fetchDailySummaries?deviceId`, `GET /v2/actions/playSummary/fetchLatestMonthlySummary?deviceId`, `GET /v2/actions/playSummary/fetchMonthlySummary?deviceId&year&month&containLatest`, `GET /v3/actions/parentalControlSetting/fetchParentalControlSetting?deviceId`, `GET /v3/actions/device/fetchExtraPlayingTimeState?deviceId`, `POST /v3/actions/parentalControlSetting/updatePlayTimer`, `POST /v2/actions/parentalControlSetting/updateRestrictionLevel`, `POST /v2/actions/parentalControlSetting/updateUnlockCode`, `POST /v2/actions/device/updateExtraPlayingTime` (`status` TO_ADDED/TO_INFINITY/TO_CANCELED, `additionalTime`), `POST /v2/actions/device/confirmExtraPlayingTime`, `POST /v3/actions/device/updateDeviceLabel` (`deviceId`, `label`), `POST /v3/actions/device/unregisterDevice`, `POST /v2/actions/deviceFederation/startDeviceFederation` (sem corpo → `deviceId`, `pairingCode`), `GET /v3/actions/deviceFederation/checkDeviceFederation?deviceId` (`pairingStatus` PAIRING/PAIRED/EXPIRED), `POST /v3/actions/federation` (`smartDeviceInfo`), chat/câmera do Switch 2 (`/v2|v3/actions/chat/*`), `sharedParentalControl/*`.
- `platformGeneration`: `P00` Switch, `P01` Switch 2. `extraPlayingTime`: `{inOneDay:{duration,isInfinity}, bedtime:{endTime}, expiresAt}`.
- Bedtime: `endingTime` = alarme (16–23h), `startingTime` = fim (05–09h).

## Descartados
- **Savanna GraphQL** (`wb.lp1.savanna.srv.nintendo.net/graphql`, header `X-Nintendo-Savanna-Client-Id: cb610bc1…`): consoles c/ serial/imagem, 46 cartões de jogo virtuais, assinatura NSO, licenças. Exige `idToken` com `aud=e56201e414c97a10`, emitido só na sessão web do portal (`/api/1.0.0/token` com cookie+CSRF). Tokens de app → `JWT_VERIFY_FAILED`; o client não aceita `session_token_code` ("Acesso inválido").
- **Coral** (app Nintendo Switch / NSO 3.5): toda requisição cifrada via servidor de terceiros (nxapi-znca-api, exige cadastro OAuth), presença do próprio usuário não é mais retornada (só de amigos, exige conta secundária), e o config remoto do nxapi está com `coral: null`.
- **Bateria/brilho/volume**: não existem em nenhuma API de nuvem. Só local (sysmodule em console desbloqueado, ex. switch-assistant).
