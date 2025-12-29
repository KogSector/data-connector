# Auth0 Setup Guide for ConHub Microservices

This guide explains how to configure Auth0 for use with ConHub data-connector and other microservices.

## Prerequisites

- Auth0 account (free tier works for development)
- Access to Auth0 Dashboard: https://manage.auth0.com

## Step 1: Create an API

1. Go to **APIs** → **Create API**
2. Configure:
   - **Name**: `ConHub API`
   - **Identifier**: `https://api.conhub.dev`
   - **Signing Algorithm**: RS256

3. Under **Permissions** tab, add scopes:
   | Permission | Description |
   |------------|-------------|
   | `read:connectors` | Read connector configurations |
   | `write:connectors` | Create/update connectors |
   | `delete:connectors` | Delete connectors |
   | `admin:all` | Full admin access |

## Step 2: Create Application

1. Go to **Applications** → **Create Application**
2. Choose **Regular Web Application**
3. In **Settings** tab:
   - Note the **Client ID** and **Client Secret**
   - **Allowed Callback URLs**: `http://localhost:3000/callback`
   - **Allowed Logout URLs**: `http://localhost:3000`
   - **Allowed Web Origins**: `http://localhost:3000`

## Step 3: Configure Machine-to-Machine (M2M) for Services

For service-to-service authentication:

1. Go to **Applications** → **Create Application**
2. Choose **Machine to Machine**
3. Select the **ConHub API** created in Step 1
4. Grant required scopes

## Step 4: Environment Variables

Add these to your `.env` file:

```bash
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_ISSUER=https://your-tenant.auth0.com/
AUTH0_AUDIENCE=https://api.conhub.dev
AUTH0_JWKS_URI=https://your-tenant.auth0.com/.well-known/jwks.json

# For ConHub internal tokens (optional, for service-to-service)
CONHUB_AUTH_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
```

## Current ConHub Auth0 Configuration

The existing setup uses:

| Setting | Value |
|---------|-------|
| Domain | `dev-pmspwseo1uaudyoi.jp.auth0.com` |
| Issuer | `https://dev-pmspwseo1uaudyoi.jp.auth0.com/` |
| Audience | `https://api.conhub.dev` |
| JWKS URI | `https://dev-pmspwseo1uaudyoi.jp.auth0.com/.well-known/jwks.json` |

## Testing Authentication

### Get a Test Token

Using Auth0's Test Token feature:
1. Go to your **API** → **Test** tab
2. Copy the generated test token

### Test Protected Endpoint

```bash
# With token
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:3013/connectors

# Without token (should return 401)
curl http://localhost:3013/connectors
```

## Debugging

### Common Issues

1. **"Invalid audience"**: Ensure `AUTH0_AUDIENCE` matches the API Identifier
2. **"Invalid issuer"**: Ensure `AUTH0_ISSUER` ends with `/`
3. **"Token expired"**: Tokens have short expiry, get a fresh one

### Verify JWKS Endpoint

```bash
curl https://your-tenant.auth0.com/.well-known/jwks.json
```

Should return JSON with `keys` array containing RSA public keys.
