import { FlatCompat } from '@eslint/eslintrc'

const compat = new FlatCompat({ baseDirectory: import.meta.dirname })

const config = [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts', 'public/**'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      'no-restricted-syntax': [
        'error',
        {
          // Rule 7 in CLAUDE.md: the OpenAI key never reaches the browser.
          selector:
            "MemberExpression[object.name='env'][property.name=/^NEXT_PUBLIC_.*(KEY|SECRET|TOKEN)/]",
          message: 'Secrets must never be exposed under a NEXT_PUBLIC_ prefix.',
        },
      ],
    },
  },
]

export default config
