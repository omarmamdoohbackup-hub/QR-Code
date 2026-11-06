/**
 * Vercel Serverless Function: /api/verify
 * Handles card verification securely using Supabase secret key on server-side only.
 */

module.exports = async function handler(req, res) {
  // Set CORS headers
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version'
  );

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ valid: false, reason: 'METHOD_NOT_ALLOWED' });
  }

  try {
    // Parse request body
    let body = req.body;
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch (e) {
        return res.status(400).json({ valid: false, reason: 'INVALID_JSON' });
      }
    }

    const token = body && typeof body.token === 'string' ? body.token.trim() : null;

    if (!token) {
      return res.status(400).json({ valid: false, reason: 'TOKEN_REQUIRED' });
    }

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseSecretKey = process.env.SUPABASE_SECRET_KEY;

    if (!supabaseUrl || !supabaseSecretKey) {
      console.error('Missing SUPABASE_URL or SUPABASE_SECRET_KEY environment variables');
      return res.status(500).json({ valid: false, reason: 'SERVER_CONFIG_ERROR' });
    }

    const cleanBaseUrl = supabaseUrl.replace(/\/+$/, '');

    const commonHeaders = {
      'apikey': supabaseSecretKey,
      'Authorization': `Bearer ${supabaseSecretKey}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    // 1. Check if token exists in cards table
    const queryUrl = `${cleanBaseUrl}/rest/v1/cards?token=eq.${encodeURIComponent(token)}&select=id,card_number,token,status,scanned_at,card_type`;
    
    const fetchResponse = await fetch(queryUrl, {
      method: 'GET',
      headers: commonHeaders
    });

    if (!fetchResponse.ok) {
      const errText = await fetchResponse.text();
      console.error('Supabase query error:', fetchResponse.status, errText);
      return res.status(500).json({ valid: false, reason: 'DATABASE_ERROR' });
    }

    const cards = await fetchResponse.json();

    // CASE 3: Card token not found
    if (!cards || cards.length === 0) {
      return res.status(200).json({
        valid: false,
        reason: 'NOT_FOUND'
      });
    }

    const card = cards[0];

    // Helper to ensure timestamp string has explicit UTC 'Z' timezone if missing
    const ensureUtcIso = (ts) => {
      if (!ts) return ts;
      let s = String(ts).trim();
      if (!/Z$/i.test(s) && !/[+-]\d{2}(:\d{2})?$/.test(s)) {
        s = s.replace(' ', 'T') + 'Z';
      }
      return s;
    };

    const cardType = card.card_type || null;

    // CASE 1: Card exists and is UNUSED
    if (card.status === 'UNUSED') {
      const nowIso = new Date().toISOString();
      const updateUrl = `${cleanBaseUrl}/rest/v1/cards?token=eq.${encodeURIComponent(token)}&status=eq.UNUSED`;
      
      const updateResponse = await fetch(updateUrl, {
        method: 'PATCH',
        headers: {
          ...commonHeaders,
          'Prefer': 'return=representation'
        },
        body: JSON.stringify({
          status: 'USED',
          scanned_at: nowIso
        })
      });

      if (!updateResponse.ok) {
        const updateErr = await updateResponse.text();
        console.error('Supabase update error:', updateResponse.status, updateErr);
        return res.status(500).json({ valid: false, reason: 'UPDATE_FAILED' });
      }

      const updatedCards = await updateResponse.json();

      // If successfully updated by this request
      if (updatedCards && updatedCards.length > 0) {
        const updatedCard = updatedCards[0];
        return res.status(200).json({
          valid: true,
          card_number: updatedCard.card_number,
          card_type: updatedCard.card_type !== undefined ? updatedCard.card_type : cardType,
          status: 'USED',
          scanned_at: ensureUtcIso(updatedCard.scanned_at) || nowIso
        });
      } else {
        // Race condition: another request just updated this card
        return res.status(200).json({
          valid: false,
          reason: 'ALREADY_USED',
          card_number: card.card_number,
          card_type: cardType,
          scanned_at: ensureUtcIso(card.scanned_at) || nowIso
        });
      }
    }

    // CASE 2: Card exists but is already USED
    return res.status(200).json({
      valid: false,
      reason: 'ALREADY_USED',
      card_number: card.card_number,
      card_type: cardType,
      scanned_at: ensureUtcIso(card.scanned_at)
    });

  } catch (error) {
    console.error('Unhandled server error in verify endpoint:', error);
    return res.status(500).json({
      valid: false,
      reason: 'INTERNAL_ERROR',
      message: error.message
    });
  }
};
