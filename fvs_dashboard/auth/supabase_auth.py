"""
Autenticação via Supabase — Email/senha + Google OAuth + whitelist de e-mails.

Configurar nos secrets/env:
    SUPABASE_URL  = "https://xxxx.supabase.co"
    SUPABASE_KEY  = "eyJ..."  # chave anon pública

SQL para criar a tabela de emails autorizados no Supabase:
    CREATE TABLE IF NOT EXISTS public.authorized_emails (
        email      TEXT PRIMARY KEY,
        nome       TEXT DEFAULT '',
        role       TEXT DEFAULT 'viewer',   -- 'admin' ou 'viewer'
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE public.authorized_emails ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "Public select" ON public.authorized_emails FOR SELECT USING (true);
    CREATE POLICY "Service role write" ON public.authorized_emails
        FOR ALL USING (auth.role() = 'service_role');

    -- Adicionar emails iniciais:
    INSERT INTO public.authorized_emails (email, nome, role) VALUES
        ('elrik@r21empreendimentos.com', 'Elrik', 'admin')
    ON CONFLICT (email) DO NOTHING;
"""
from __future__ import annotations

import streamlit as st

try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_PKG = True
except ImportError:
    _SUPABASE_PKG = False


class SupabaseAuth:
    """Wrapper de autenticação Supabase para o FVS Dashboard."""

    def __init__(self, url: str, key: str, allowed_domains: str = "") -> None:
        """
        allowed_domains: domínios liberados separados por vírgula.
            Ex.: "r21empreendimentos.com,r21engenharia.com"
            Qualquer email @domínio é autorizado automaticamente.
        """
        if not _SUPABASE_PKG:
            raise ImportError(
                "Pacote 'supabase' não encontrado. Execute: pip install supabase>=2.0.0"
            )
        self._url = url
        self._key = key
        # Normaliza lista de domínios: lower, sem espaços, sem vazios
        self.allowed_domains: list[str] = [
            d.strip().lower()
            for d in allowed_domains.split(",")
            if d.strip()
        ]
        self.client: SupabaseClient = create_client(url, key)

    # ── Login / Logout ────────────────────────────────────────────────────────

    def login(self, email: str, password: str):
        """
        Autentica com email e senha.
        Retorna o objeto `user` (supabase) ou lança exceção.
        """
        resp = self.client.auth.sign_in_with_password(
            {"email": email.strip().lower(), "password": password}
        )
        return resp.user

    def signup(self, email: str, password: str, nome: str = ""):
        """
        Cria nova conta. Só permite se o email estiver na whitelist.
        Retorna o objeto `user` ou lança exceção.
        """
        email = email.strip().lower()
        if not self.is_authorized(email):
            raise PermissionError(
                f"O e-mail '{email}' não está autorizado a criar conta. "
                "Solicite acesso ao administrador."
            )
        options: dict = {}
        if nome:
            options = {"data": {"full_name": nome.strip()}}
        resp = self.client.auth.sign_up(
            {"email": email, "password": password, "options": options}
        )
        return resp.user

    def logout(self) -> None:
        """Encerra a sessão atual."""
        try:
            self.client.auth.sign_out()
        except Exception:
            pass
        for key in ("auth_user", "auth_email", "auth_nome", "auth_role"):
            st.session_state.pop(key, None)

    # ── Google OAuth ──────────────────────────────────────────────────────────

    def google_auth_url(self, redirect_url: str) -> str:
        """
        Gera a URL de autenticação via Google (OAuth 2.0 implícito).
        Redirecionar o navegador para esta URL inicia o fluxo Google.
        Após autenticação, o Supabase redireciona para `redirect_url`
        com os tokens no fragmento da URL (#access_token=...).
        """
        resp = self.client.auth.sign_in_with_oauth(
            {
                "provider": "google",
                "options": {"redirect_to": redirect_url},
            }
        )
        return resp.url

    def set_session_from_token(self, access_token: str, refresh_token: str):
        """
        Restaura a sessão a partir de tokens OAuth recebidos no callback.
        Retorna o objeto `user` ou lança exceção.
        Se o access_token estiver expirado, o Supabase usa o refresh_token
        automaticamente para emitir um novo par de tokens.
        """
        resp = self.client.auth.set_session(access_token, refresh_token)
        return resp.user

    def get_session_tokens(self) -> tuple[str, str]:
        """
        Retorna (access_token, refresh_token) da sessão atual.
        Usar para salvar no localStorage após login por email/senha.
        """
        try:
            session = self.client.auth.get_session()
            if session:
                return session.access_token or "", session.refresh_token or ""
        except Exception:
            pass
        return "", ""

    # ── Whitelist ─────────────────────────────────────────────────────────────

    def is_authorized(self, email: str) -> bool:
        """
        Verifica se o email tem acesso. Ordem de verificação:
        1. Domínio liberado (allowed_domains) → acesso imediato
        2. Email individual na tabela authorized_emails
        """
        email = email.strip().lower()

        # 1. Domínio liberado?
        if self.allowed_domains:
            email_domain = email.split("@")[-1] if "@" in email else ""
            if email_domain in self.allowed_domains:
                return True

        # 2. Email individual na whitelist
        try:
            result = (
                self.client.table("authorized_emails")
                .select("email")
                .eq("email", email)
                .execute()
            )
            return len(result.data) > 0
        except Exception:
            # Em caso de falha na consulta, negar acesso por segurança
            return False

    def get_role(self, email: str) -> str:
        """
        Retorna o role do email ('admin', 'viewer').
        - Email na whitelist → usa o role cadastrado
        - Email autorizado apenas por domínio → 'viewer' por padrão
        """
        email = email.strip().lower()
        try:
            result = (
                self.client.table("authorized_emails")
                .select("role")
                .eq("email", email)
                .execute()
            )
            if result.data:
                return result.data[0].get("role", "viewer")
        except Exception:
            pass
        # Domínio liberado mas sem entrada individual → viewer
        return "viewer"

    def list_authorized(self) -> list[dict]:
        """Lista todos os emails autorizados."""
        try:
            result = (
                self.client.table("authorized_emails")
                .select("*")
                .order("email")
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def add_authorized(self, email: str, nome: str = "", role: str = "viewer") -> None:
        """Adiciona email à whitelist (uso admin)."""
        self.client.table("authorized_emails").insert(
            {"email": email.strip().lower(), "nome": nome.strip(), "role": role}
        ).execute()

    def remove_authorized(self, email: str) -> None:
        """Remove email da whitelist (uso admin)."""
        self.client.table("authorized_emails").delete().eq(
            "email", email.strip().lower()
        ).execute()
