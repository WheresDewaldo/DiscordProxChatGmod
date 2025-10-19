if SERVER then
    CreateConVar("proxchat_bridge_url", "http://127.0.0.1:8080", FCVAR_ARCHIVE, "Base URL for the proximity chat bridge")
    CreateConVar("proxchat_bridge_secret", "", FCVAR_ARCHIVE, "Shared secret for the proximity chat bridge")
    CreateConVar("proxchat_pos_hz", "2", FCVAR_ARCHIVE, "Position batch frequency in Hz (2-5 recommended)")

    util.AddNetworkString("proxchat_debug")

    local function http_post(path, bodyTbl)
        local base = GetConVar("proxchat_bridge_url"):GetString()
        local secret = GetConVar("proxchat_bridge_secret"):GetString()
        local url = string.TrimRight(base, "/") .. path
        local body = util.TableToJSON(bodyTbl)
        HTTP({
            url = url,
            method = "POST",
            body = body,
            headers = {
                ["Content-Type"] = "application/json",
                ["x-bridge-secret"] = secret,
            },
            success = function(_, code)
                if code ~= 200 then
                    print("[ProxChat] Bridge POST failed: " .. tostring(code))
                end
            end,
            failed = function(err)
                print("[ProxChat] Bridge POST error: " .. tostring(err))
            end
        })
    end

    local function emit_event(ev)
        http_post("/events", ev)
    end

    hook.Add("TTTBeginRound", "ProxChat_TTTBeginRound", function()
        emit_event({ type = "round_start", ts = CurTime(), round_id = tostring(os.time()) })
    end)

    hook.Add("TTTEndRound", "ProxChat_TTTEndRound", function()
        emit_event({ type = "round_end", ts = CurTime() })
    end)

    hook.Add("PlayerSpawn", "ProxChat_PlayerSpawn", function(ply)
        if not IsValid(ply) or not ply.SteamID64 then return end
        emit_event({ type = "player_spawn", ts = CurTime(), player = { steamid64 = ply:SteamID64() } })
    end)

    hook.Add("PlayerDeath", "ProxChat_PlayerDeath", function(victim, inflictor, attacker)
        if not IsValid(victim) or not victim.SteamID64 then return end
        emit_event({ type = "player_death", ts = CurTime(), player = { steamid64 = victim:SteamID64() } })
    end)

    -- In-game linking: user runs /linksteam in Discord to get a code, then types !link CODE in GMod chat
    hook.Add("PlayerSay", "ProxChat_LinkSteam", function(ply, text)
        if not IsValid(ply) or not ply.SteamID64 then return end
        if not isstring(text) then return end
        local trimmed = string.Trim(text)
        local code = string.match(trimmed, "^!link%s+([A-Fa-f0-9]+)$")
        if not code then return end
        emit_event({ type = "link_attempt", ts = CurTime(), code = code, player = { steamid64 = ply:SteamID64() } })
        return "" -- optionally hide the chat message
    end)

    -- periodic position batching
    local accum = 0
    hook.Add("Think", "ProxChat_PosBatchThink", function()
        local hz = math.Clamp(GetConVar("proxchat_pos_hz"):GetInt(), 1, 10)
        local interval = 1 / hz
        accum = accum + FrameTime()
        if accum < interval then return end
        accum = 0
        local positions = {}
        for _, ply in ipairs(player.GetAll()) do
            if IsValid(ply) and ply:IsFullyAuthenticated() and ply:Alive() then
                local pos = ply:GetPos()
                table.insert(positions, {
                    player = { steamid64 = ply:SteamID64() },
                    pos = { x = pos.x, y = pos.y, z = pos.z },
                    ts = CurTime(),
                })
            end
        end
        if #positions > 0 then
            emit_event({ type = "player_pos_batch", positions = positions })
        end
    end)
end