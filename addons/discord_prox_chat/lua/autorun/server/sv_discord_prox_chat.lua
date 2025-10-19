if SERVER then
    print("[ProxChat] Loading Discord Proximity Chat addon...")
    CreateConVar("proxchat_bridge_url", "http://127.0.0.1:8085", FCVAR_ARCHIVE, "Base URL for the proximity chat bridge")
    CreateConVar("proxchat_bridge_secret", "", FCVAR_ARCHIVE, "Shared secret for the proximity chat bridge")
    CreateConVar("proxchat_pos_hz", "2", FCVAR_ARCHIVE, "Position batch frequency in Hz (2-5 recommended)")
    CreateConVar("proxchat_include_spectators", "0", FCVAR_ARCHIVE, "When enabled, include spectators in position batches (for testing)")
    CreateConVar("proxchat_autounspect", "0", FCVAR_ARCHIVE, "If enabled, auto-clear spectator-only for new players so rounds can start")
    CreateConVar("proxchat_enabled", "1", FCVAR_ARCHIVE, "Enable/disable ProxChat addon hooks without unloading")

    util.AddNetworkString("proxchat_debug")

    local function get_cvar_str(name, default)
        local cv = GetConVar and GetConVar(name)
        if cv and cv.GetString then
            local val = cv:GetString()
            if val ~= nil and val ~= "" then return val end
        end
        return default
    end

    local function http_post(path, bodyTbl)
        local base = get_cvar_str("proxchat_bridge_url", "http://127.0.0.1:8085")
        local secret = get_cvar_str("proxchat_bridge_secret", "")
        local url = string.TrimRight(base, "/") .. path
        local body = util.TableToJSON(bodyTbl)
        print(string.format("[ProxChat] POST %s (type=%s)", url, tostring(bodyTbl and bodyTbl.type)))
        HTTP({
            url = url,
            method = "POST",
            body = body,
            headers = {
                ["Content-Type"] = "application/json",
                ["x-bridge-secret"] = secret,
            },
            success = function(data, code)
                if code ~= 200 then
                    print("[ProxChat] Bridge POST failed: " .. tostring(code))
                else
                    -- print success for link_attempts
                    if bodyTbl and bodyTbl.type == "link_attempt" then
                        print("[ProxChat] Bridge POST ok for link_attempt")
                        local ok, resp = pcall(util.JSONToTable, data or "")
                        if ok and istable(resp) then
                            if resp.linked == true then
                                -- Notify all players? Better to target the caller, but we don't have ref here
                                print("[ProxChat] Link succeeded per bridge response")
                            elseif resp.linked == false then
                                print("[ProxChat] Link failed per bridge response: " .. tostring(resp.reason))
                            end
                        end
                    end
                end
            end,
            failed = function(err)
                print("[ProxChat] Bridge POST error: " .. tostring(err))
            end
        })
    end

    local function is_enabled()
        local cv = GetConVar("proxchat_enabled")
        return cv and cv:GetBool()
    end

    local function emit_event(ev)
        if not is_enabled() then return end
        http_post("/events", ev)
    end

    local round_active = false

    hook.Add("TTTBeginRound", "ProxChat_TTTBeginRound", function()
        if not is_enabled() then return end
        round_active = true
        print("[ProxChat] TTTBeginRound fired; round_active=true")
        emit_event({ type = "round_start", ts = CurTime(), round_id = tostring(os.time()) })
    end)

    hook.Add("TTTEndRound", "ProxChat_TTTEndRound", function()
        if not is_enabled() then return end
        round_active = false
        print("[ProxChat] TTTEndRound fired; round_active=false")
        emit_event({ type = "round_end", ts = CurTime() })
    end)

    hook.Add("PlayerSpawn", "ProxChat_PlayerSpawn", function(ply)
        if not is_enabled() then return end
        if not IsValid(ply) or not ply.SteamID64 then return end
        emit_event({ type = "player_spawn", ts = CurTime(), player = { steamid64 = ply:SteamID64() } })
    end)

    hook.Add("PlayerDeath", "ProxChat_PlayerDeath", function(victim, inflictor, attacker)
        if not is_enabled() then return end
        if not IsValid(victim) or not victim.SteamID64 then return end
        emit_event({ type = "player_death", ts = CurTime(), player = { steamid64 = victim:SteamID64() } })
    end)

    -- In-game linking: user runs /linksteam in Discord to get a code, then types !link CODE in GMod chat
    hook.Add("PlayerSay", "ProxChat_LinkSteam", function(ply, text)
        if not IsValid(ply) or not ply.SteamID64 then return end
        if not isstring(text) then return end
        local trimmed = string.Trim(text)
        -- Accept a variety of styles: !link CODE, !link <CODE>, extra spaces ok
        local raw = string.match(trimmed, "^!link%s+<?([^%s>]+)>?%s*$")
        if not raw then return end
        local code = string.upper(string.Trim(raw))
        print(string.format("[ProxChat] !link detected from %s (%s): %s", ply:Nick(), ply:SteamID64(), code))
        -- Validate hex-only (our codes are 6 hex chars)
        if not string.match(code, "^[A-F0-9]+$") then
            ply:ChatPrint("[ProxChat] Invalid code format. Use /linksteam in Discord to get a code, then type !link CODE here.")
            return "" -- suppress echo
        end
        -- Capture player for callback feedback
        local sid = ply:SteamID64()
        HTTP({
            url = string.TrimRight(get_cvar_str("proxchat_bridge_url", "http://127.0.0.1:8085"), "/") .. "/events",
            method = "POST",
            body = util.TableToJSON({ type = "link_attempt", ts = CurTime(), code = code, player = { steamid64 = sid } }),
            headers = {
                ["Content-Type"] = "application/json",
                ["x-bridge-secret"] = get_cvar_str("proxchat_bridge_secret", ""),
            },
            success = function(data, code)
                if code ~= 200 then
                    ply:ChatPrint("[ProxChat] Bridge request failed (" .. tostring(code) .. ")")
                    return
                end
                local ok, resp = pcall(util.JSONToTable, data or "")
                if ok and istable(resp) then
                    if resp.linked == true then
                        ply:ChatPrint("[ProxChat] Linked! You should receive a DM in Discord.")
                    elseif resp.linked == false then
                        local reason = tostring(resp.reason or "unknown")
                        if reason == "code_not_found" then
                            ply:ChatPrint("[ProxChat] That code was not found. Generate a new one with /linksteam in Discord.")
                        elseif reason == "code_expired" then
                            ply:ChatPrint("[ProxChat] That code expired. Generate a new one with /linksteam in Discord.")
                        else
                            ply:ChatPrint("[ProxChat] Link failed (" .. reason .. ").")
                        end
                    else
                        ply:ChatPrint("[ProxChat] Bridge responded unexpectedly.")
                    end
                else
                    ply:ChatPrint("[ProxChat] Invalid response from bridge.")
                end
            end,
            failed = function(err)
                ply:ChatPrint("[ProxChat] Bridge error: " .. tostring(err))
            end
        })
        -- Hide the chat message either way
        return "" -- always hide the chat message
    end)

    -- Console test command: proxchat_link <steamid64> <code>
    concommand.Add("proxchat_link", function(ply, cmd, args)
        if IsValid(ply) then
            ply:ChatPrint("[ProxChat] This command is server console only.")
            return
        end
        local sid = tostring(args[1] or "")
        local code = string.upper(string.Trim(tostring(args[2] or "")))
        if sid == "" or code == "" then
            print("[ProxChat] Usage: proxchat_link <steamid64> <code>")
            return
        end
        if not string.match(code, "^[A-F0-9]+$") then
            print("[ProxChat] Invalid code format; expected hex.")
            return
        end
        print(string.format("[ProxChat] Console link attempt sid=%s code=%s", sid, code))
        emit_event({ type = "link_attempt", ts = CurTime(), code = code, player = { steamid64 = sid } })
    end)

    -- periodic position batching
    local accum = 0
    hook.Add("Think", "ProxChat_PosBatchThink", function()
        if not is_enabled() then return end
        if not round_active then return end
        local hz = math.Clamp(GetConVar("proxchat_pos_hz"):GetInt(), 1, 10)
        local interval = 1 / hz
        accum = accum + FrameTime()
        if accum < interval then return end
        accum = 0
        local positions = {}
        for _, ply in ipairs(player.GetAll()) do
            if not IsValid(ply) or not ply:IsFullyAuthenticated() then
                -- skip invalid or unauthenticated players
            else
                local include_spect = GetConVar("proxchat_include_spectators"):GetBool()
                if not include_spect and not ply:Alive() then
                    -- skip spectators unless explicitly enabled
                else
                    local pos = ply:GetPos()
                    table.insert(positions, {
                        player = { steamid64 = ply:SteamID64() },
                        pos = { x = pos.x, y = pos.y, z = pos.z },
                        ts = CurTime(),
                    })
                end
            end
        end
        if #positions > 0 then
            emit_event({ type = "player_pos_batch", positions = positions })
        end
    end)

    -- Optional: auto-clear spectator-only for new players (does not run unless enabled)
    hook.Add("PlayerInitialSpawn", "ProxChat_AutoUnspect", function(ply)
        local cv = GetConVar("proxchat_autounspect")
        if not cv or not cv:GetBool() then return end
        if not IsValid(ply) then return end
        -- Delay slightly to let TTT initialize player state
        timer.Simple(2, function()
            if not IsValid(ply) then return end
            local isSpec = false
            if ply.IsSpec then
                local ok, val = pcall(function() return ply:IsSpec() end)
                isSpec = ok and val == true
            end
            if isSpec then
                ply:ConCommand("ttt_spectate 0")
                -- Note: use dot for existence check and colon for invocation; wrap in parens for precedence
                print(string.format("[ProxChat] Auto-unspect applied to %s (%s)", ply:Nick(), (ply.SteamID64 and ply:SteamID64()) or "?"))
            end
        end)
    end)
end